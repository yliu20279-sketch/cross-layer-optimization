"""Small P0 software checks, never a model/native/timing acceptance suite."""
import copy
import itertools
import json
import random
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.common import ContractError, digest
from core.scheduling import validate_split, train_placement, DecisionInput, decide, route_after_router
from core.collectives import shuffled_reduce_scatter, shuffled_allgather
from core.graph import communication_scope, dispatch_combine, layer_dag
from core.memory import Residency, check_residency, split_pages, tensor_bytes, validate_mapping
from core.coaccess import build_profile, optimize
from core.runtime import ModeController, MODES, controls, ns_to_ticks, aggregate_costs, COSTS
from core.reuse import compare_contracts, FIELDS, verify_manifest
from core.readiness import preflight
from core.capture import validate_capture


def training_rows(layers=2, experts=4):
    return [{"split": split, "request_id": req, "source_sha256": source * 64,
             "input_tokens_sha256": tokens * 64, "layer": layer, "token_id": token,
             "expert": (token + layer) % experts, "count": 1}
            for split, req, source, tokens in (("profile", "p", "a", "b"), ("eval", "e", "c", "d"))
            for layer in range(layers) for token in range(6)]


def pair(request, owner, obj, offset, size, start, done, tx=0):
    base = {"request_id": request, "owner": owner, "object_id": obj, "partition": 0,
            "generation": 0, "op_id": obj, "transaction_id": tx, "offset": offset,
            "bytes": size, "object_bytes": 8192, "role": "weight", "router": False}
    return [dict(base, event="accept", time=start), dict(base, event="callback", time=done)]


class ContractChecks(unittest.TestCase):
    def test_q15_authorized_decoded_fp16_is_distinct_from_original_and_packed(self):
        from models.qwen15.capture_contract import validate
        from models.qwen15 import SPEC
        from models.qwen15.memory_lowering import operand_reads
        metadata = {"model_id": SPEC["id"], "variant": "gptq_decoded_fp16", "quantization": None,
                    "source_quantization": "GPTQ_INT4", "weight_dtype": "F16",
                    "decoded_manifest_sha256": "d" * 64, "checkpoint_content_sha256": "c" * 64,
                    "tokenizer_sha256": "a" * 64, "revision": "content-snapshot-fixture",
                    "traffic_mode": "teacher_forced", "phase": "decode", "is_performance_measurement": False}
        self.assertFalse(validate(metadata, training_rows())["timing_claim"])
        for change in ({"weight_dtype": "BF16"}, {"quantization": "GPTQ"}, {"decoded_manifest_sha256": None},
                       {"model_id": "Qwen/Qwen1.5-MoE-A2.7B"}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate(dict(metadata, **change), training_rows())
        obj = {"w": {"dtype": "F16", "shape": [3, 7], "bytes": 42, "header_sha256": "f" * 64}}
        self.assertEqual(sum(x["bytes"] for x in operand_reads(obj, "w", 0, 42)), 42)
    def test_capture_identity_rejects_model_and_quantized_substitutions(self):
        model = "Qwen/Qwen1.5-MoE-A2.7B"
        metadata = {"model_id": model, "variant": "original", "quantization": None,
                    "weight_dtype": "BF16", "checkpoint_content_sha256": "c" * 64,
                    "tokenizer_sha256": "a" * 64, "revision": "fixture-revision",
                    "traffic_mode": "teacher_forced", "phase": "decode",
                    "is_performance_measurement": False}
        self.assertFalse(validate_capture(metadata, training_rows(), model)["timing_claim"])
        for change in ({"model_id": model + "-Chat-GPTQ-Int4"}, {"quantization": "GPTQ"},
                       {"checkpoint_content_sha256": None}, {"weight_dtype": "F16"}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate_capture(dict(metadata, **change), training_rows(), model)

    def test_split_rejects_missing_overlap_and_duplicate_identity(self):
        rows = training_rows()
        self.assertEqual(validate_split(rows)["profile"], ["p"])
        for mutation in ("no_eval", "source_overlap", "token_overlap", "unknown_split", "duplicate_id"):
            bad = copy.deepcopy(rows)
            if mutation == "no_eval":
                bad = [x for x in bad if x["split"] == "profile"]
            elif mutation in ("source_overlap", "token_overlap"):
                field = "source_sha256" if mutation == "source_overlap" else "input_tokens_sha256"
                for x in bad:
                    if x["split"] == "eval":
                        x[field] = rows[0][field]
            elif mutation == "unknown_split":
                bad[0]["split"] = "synthetic"
            else:
                bad += [dict(x, request_id="renamed") for x in rows if x["split"] == "eval"]
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                validate_split(bad)

    def test_eval_routes_do_not_affect_training_or_decisions(self):
        rows = training_rows()
        a = train_placement([x for x in rows if x["split"] == "profile"], 2, 4, 2)
        changed = copy.deepcopy(rows)
        for x in changed:
            if x["split"] == "eval":
                x["expert"] = (x["expert"] + 2) % 4
        b = train_placement([x for x in changed if x["split"] == "profile"], 2, 4, 2)
        self.assertEqual(a, b)
        data = DecisionInput("e", 0, 2, 0, 10, 11)
        self.assertEqual(decide(a, data), decide(b, data))
        with self.assertRaises(ContractError):
            train_placement(changed, 2, 4, 2)
        with self.assertRaises(ContractError):
            decide(a, DecisionInput("e", 0, 2, 0, 12, 11))

    def test_unknown_tokens_and_tampered_decision(self):
        p = train_placement([x for x in training_rows() if x["split"] == "profile"], 2, 4, 2)
        decision = decide(p, DecisionInput("e", 0, 99, 0, 0, 1))
        self.assertTrue(decision["unknown_token"])
        self.assertEqual(decision["rank"], 1)
        good = route_after_router(p, decision, [0, 2], [.2, .8], 2)
        self.assertEqual([x["slot"] for x in good], [0, 1])
        bad = dict(decision, rank=0)
        with self.assertRaises(ContractError):
            route_after_router(p, bad, [0, 2], [.2, .8], 2)
        with self.assertRaises(ContractError):
            route_after_router(p, decision, [0, 2], [.2, .8], .5)

    def test_srs_sag_restore_token_identity_for_all_small_assignments(self):
        partials = [[[10 * rank + token, 100 * rank - token] for token in range(3)] for rank in range(3)]
        expected = [[sum(partials[r][t][d] for r in range(3)) for d in range(2)] for t in range(3)]
        for destinations in itertools.product(range(3), repeat=3):
            shards = shuffled_reduce_scatter(partials, destinations, lambda a, b: a + b)
            self.assertEqual(shuffled_allgather(shards, 3), expected)
        with self.assertRaises(ContractError):
            shuffled_allgather([[(0, [1])], [(0, [2])]], 1)

    def test_qwen_model_topk_shared_and_tp_dag(self):
        from models.qwen3.build_graph import build_layer as q3
        from models.qwen15.build_graph import build_layer as q15
        for build, layers, experts, ep, topk, shared in ((q3, 48, 128, 16, 8, False), (q15, 24, 60, 4, 4, True)):
            profile = [x for x in training_rows(layers, experts) if x["split"] == "profile"]
            p = train_placement(profile, layers, experts, ep)
            decision = decide(p, DecisionInput("e", 0, 1, layers - 1, 0, 1))
            graph = build(p, decision, list(range(topk)), [1 / topk] * topk, 2, "hiband_sem_moe")
            self.assertEqual(any(n["id"] == "shared_mul" for n in graph["nodes"]), shared)
            self.assertIn(("slot_sum", "sag"), graph["edges"])
            self.assertFalse(graph["target_opcode_lowering"])
            with self.assertRaises(ContractError):
                build(p, decision, [0], [1], 2, "hiband_sem_moe")

    def test_scope_and_all_peer_payload_conservation(self):
        self.assertEqual(communication_scope("hiband", 3, 4), "global")
        self.assertEqual(communication_scope("hiband", 0, 4), "local")
        self.assertEqual(communication_scope("sem_moe", 0, 4), "global")
        flows = [{"request_id": "r", "position": 0, "layer": 0, "slot": i,
                  "src_rank": 0, "dst_rank": i} for i in range(4)]
        packets = dispatch_combine(flows, dict(enumerate([0, 1, 4, 5])), "hiband", 4096)
        self.assertEqual(len(packets), 6)
        self.assertEqual(sum(p["bytes"] for p in packets), 6 * 4096)
        self.assertEqual({p["dst"] for p in packets if p["kind"] == "dispatch"}, {1, 4, 5})

    def test_exact_byte_chunks_and_capacity_lifetime(self):
        self.assertEqual(split_pages(4090, 20), [(0, 4090, 6), (1, 0, 14)])
        self.assertEqual(tensor_bytes([3, 7], "BF16"), 42)
        objects = [Residency("a", 0, 0, 32, 0, 2), Residency("b", 0, 0, 32, 2, 4)]
        self.assertEqual(check_residency(objects, {0: 32}), {0: 32})
        with self.assertRaises(ContractError):
            check_residency(objects + [Residency("c", 0, 16, 16, 1, 3)], {0: 32})
        with self.assertRaises(ContractError):
            check_residency([Residency("a", 0, 0, 33, 0, 2)], {0: 32})

    def test_profile_intervals_against_independent_pairwise_sum(self):
        rng = random.Random(17)
        events, intervals = [], []
        for i in range(20):
            start = rng.randrange(20)
            done = start + rng.randrange(1, 8)
            events += pair("p" + str(i), i, "o" + str(i), 0, 16, start, done)
            intervals.append((start, done, str(i)))
        events.sort(key=lambda x: (x["time"], x["event"] == "callback"))
        graph = build_profile(events, {"p" + str(i) for i in range(20)}, {"eval"})
        expected = sum(max(0, min(a[1], b[1]) - max(a[0], b[0]))
                       for a, b in itertools.combinations(intervals, 2))
        self.assertEqual(sum(w for _, _, w in graph["edges"]), expected)
        self.assertEqual(graph["valid_bytes"], 320)

    def test_profile_cross_page_and_rejected_bad_callbacks(self):
        events = pair("p", 0, "a", 4090, 20, 0, 3)
        graph = build_profile(events, {"p"}, {"e"})
        self.assertEqual(sorted(graph["heat"].values()), [6, 14])
        for bad in (events + [events[1]], events[:1], [dict(events[0], owner=-1), events[1]],
                    [dict(events[0], request_id="e"), events[1]]):
            with self.assertRaises(ContractError):
                build_profile(bad, {"p"}, {"e"})

    def test_optimizer_bijection_budget_determinism_and_fixed_pages(self):
        pages = {str(i): {"partition": i // 4, "bytes": 16, "movable": i != 7} for i in range(8)}
        base = {str(i): i % 4 for i in range(8)}
        decoder = {"backend_sha256": "f" * 64, "address_unit": "frame4096",
                   "frame_banks": {str(p): {str(f): f % 2 for f in range(4)} for p in range(2)}}
        profile = {"heat": {str(i): i + 1 for i in range(8)}, "edges": [["0", "2", 10], ["1", "3", 2]]}
        a = optimize(base, pages, decoder, profile, [7, 2, 9], 100, .6)
        self.assertEqual(a, optimize(base, pages, decoder, profile, [7, 2, 9], 100, .6))
        for run in a["runs"]:
            self.assertLessEqual(run["changed_payload_bytes"], a["move_budget_bytes"])
            self.assertEqual(run["mapping"]["7"], base["7"])
            validate_mapping(base, run["mapping"], pages, decoder)
        fixed = optimize(base, pages, decoder, profile, [7], 100, 0)
        self.assertEqual(fixed["selected"]["mapping"], base)
        bad = dict(base, **{"0": 1})
        with self.assertRaises(ContractError):
            validate_mapping(base, bad, pages, decoder)

    def test_mode_budget_switch_drain_and_no_environment_inheritance(self):
        controller = ModeController(3)
        self.assertEqual(controller.select(20, 1, 0, 1)["mode"], "GLOBAL_BIAS")
        change = controller.select(20, 1, 0, 0)
        self.assertEqual(change["mode"], "LOCAL_BIAS")
        self.assertFalse(change["can_issue"])
        self.assertEqual(controller.select(20, 1, 3, 0)["can_issue"], True)
        self.assertTrue(all(sum(v) == 1536 for v in MODES.values()))
        self.assertNotIn("HB_FIXED_MODE", controls("hiband", 256, 270))
        self.assertEqual(controls("sem_moe", 256, 270)["HB_FIXED_MODE"], "GLOBAL_BIAS")
        self.assertEqual(ns_to_ticks(1.25, .4), 4)

    def test_missing_and_overlapping_costs_fail_closed(self):
        with self.assertRaises(ContractError):
            aggregate_costs({})
        ledger = {name: {"status": "not_applicable", "reason": "fixture", "evidence_sha256": "test"}
                  for name in COSTS}
        for i, name in enumerate(COSTS[:2]):
            ledger[name] = {"status": "measured", "evidence_sha256": "fixture", "unit": "target_ticks",
                            "clock_domain": "cpu", "exclusive_intervals": [[i * 3, i * 3 + 2]]}
        self.assertEqual(aggregate_costs(ledger), 4)
        ledger[COSTS[1]]["exclusive_intervals"] = [[1, 4]]
        with self.assertRaises(ContractError):
            aggregate_costs(ledger)

    def test_reuse_refuses_unknown_identity_even_if_equal_none(self):
        self.assertFalse(compare_contracts({}, {})["cycle_reuse_allowed"])
        old = {field: "identity-" + field for field in FIELDS}
        self.assertTrue(compare_contracts(old, dict(old))["cycle_reuse_allowed"])
        new = dict(old, precision_sha256="BF16-new")
        self.assertEqual(compare_contracts(old, new)["differences"], ["precision_sha256"])
        self.assertFalse(verify_manifest([{"path": "x", "sha256": "a"}], {"x": "b"})["pass"])

    def test_actual_model_contracts_refuse_native_admission(self):
        for model in ("qwen3", "qwen15"):
            path = ROOT / "contracts" / (model + ".json")
            contract = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(preflight(contract)["ready"])
            self.assertFalse(preflight(contract)["p0_2_started"])


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractChecks))
    report = {"status": "PASS_SOFTWARE_REFERENCE_ONLY" if result.wasSuccessful() else "FAIL",
              "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "native_runs": 0, "model_runs": 0, "p0_2_started": False}
    evidence = ROOT / "evidence" / "SOFTWARE_CHECKS.json"
    if evidence.exists():
        i = 1
        while evidence.with_name("SOFTWARE_CHECKS_attempt%d.json" % i).exists():
            i += 1
        evidence.rename(evidence.with_name("SOFTWARE_CHECKS_attempt%d.json" % i))
    evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
