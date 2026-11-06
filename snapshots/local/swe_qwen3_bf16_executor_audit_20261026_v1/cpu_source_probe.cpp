// CPU-only unit probe of the unchanged, hashed NPUSim source snapshot.
// This is not a model run, a timing simulation, or a deployed-binary test.
#include "/mnt/sda1/h3240101068/olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_runtime.cpp"
#include <iomanip>

int main() {
    using namespace NPUSim;
    std::uint64_t finite=0, mismatch=0;
    for (std::uint32_t b=0;b<65536;++b) {
        if ((b&0x7f80U)==0x7f80U) continue;
        ++finite;
        if (floatToBf16Bits(bf16BitsToFloat(static_cast<std::uint16_t>(b)))!=b) ++mismatch;
    }
    const bool ties = floatToBf16Bits(floatFromBits(0x3f808000U))==0x3f80 &&
                      floatToBf16Bits(floatFromBits(0x3f818000U))==0x3f82;
    std::vector<float> payload{1.0F,-0.0F,1.e10F};
    const auto bytes=encodeFloatTensor(payload,TensorDType::kBf16);
    nlohmann::json result;
    result["scope"]="CPU source unit probe; no model, GPU, timing simulation or deployed binary equivalence";
    result["finite_bf16_patterns"]=finite;
    result["finite_roundtrip_mismatches"]=mismatch;
    result["selected_rne_ties_pass"]=ties;
    result["three_element_payload_bytes"]=bytes.size();
    result["bf16_large_value_finite"]=std::isfinite(convertFloatForTensorDType(1.e10F,TensorDType::kBf16));
    result["fp16_same_value_overflows"]=std::isinf(convertFloatForTensorDType(1.e10F,TensorDType::kFp16));

    Model model; model.graph_inputs={"x"}; model.graph_outputs={"y"};model.value_shapes["x"]={1,3};
    Node sm;sm.name="softmax_probe";sm.op_type="Softmax";sm.inputs={"x"};sm.outputs={"y"};sm.int_attrs["axis"]=-1;
    model.nodes={sm};
    Tensor input;input.shape={1,3};input.data={1.F,2.F,3.F};
    FunctionalOnnxExecutionOptions fp32;
    auto a=executeOnnxFunctionally(model,{input},fp32);
    FunctionalOnnxExecutionOptions bf16;bf16.activation_dtype=TensorDType::kBf16;
    bf16.weight_dtype=TensorDType::kBf16;bf16.accumulator_dtype=TensorDType::kFp32;
    bf16.output_dtype=TensorDType::kFp32; // final FP32 output does not restore intermediate precision
    auto b=executeOnnxFunctionally(model,{input},bf16);
    result["softmax_fp32"]=a.output_tensors[0].data;
    result["softmax_bf16_global_activation_even_with_fp32_output"]=b.output_tensors[0].data;
    result["softmax_probabilities_differ"]=a.output_tensors[0].data!=b.output_tensors[0].data;
    nlohmann::json missing;
    for(const std::string op: {"TopK","Gather","ScatterElements","Cast","Sin","Cos"}) {
        auto m=model;m.nodes[0].op_type=op;
        try {executeOnnxFunctionally(m,{input},bf16);missing[op]="accepted";}
        catch(const std::exception& e){missing[op]=e.what();}
    }
    result["generic_runtime_operator_probe"]=missing;

    std::uint32_t state=7;std::uint64_t diffs=0; nlohmann::json example;
    for(int trial=0;trial<128;++trial) {
        Tensor x,w;x.shape=w.shape={1,8};
        for(int i=0;i<8;++i) {
            state=1664525U*state+1013904223U;
            x.data.push_back(convertFloatForTensorDType((int((state>>8)%2001)-1000)/317.F,TensorDType::kBf16));
            state=1664525U*state+1013904223U;
            w.data.push_back(convertFloatForTensorDType((int((state>>8)%2001)-1000)/911.F,TensorDType::kBf16));
        }
        auto generic=rmsNormalization(x,w,1.e-6F,-1);
        float sq=0;for(float v:x.data)sq+=v*v;
        const float inv=1.F/std::sqrt(sq/8.F+1.e-6F);
        for(int i=0;i<8;++i) {
            const float reference=convertFloatForTensorDType(convertFloatForTensorDType(x.data[i]*inv,TensorDType::kBf16)*w.data[i],TensorDType::kBf16);
            const float actual=convertFloatForTensorDType(generic.data[i],TensorDType::kBf16);
            if(reference!=actual) {
                ++diffs;
                if(example.is_null())example={{"x",x.data},{"weight",w.data},{"element",i},{"source_style_two_rounds",reference},{"generic_fused_then_round",actual}};
            }
        }
    }
    result["rmsnorm_tested_elements"]=1024;
    result["rmsnorm_boundary_difference_elements"]=diffs;
    result["rmsnorm_first_counterexample"]=example;
    result["rmsnorm_scope"]="same scalar FP32 inverse in both sides, isolates cast-before-scale vs cast-after-scale; not full GPU equivalence";
    std::cout<<result.dump(2)<<'\n';
    return mismatch==0 && ties && bytes.size()==6 ? 0:2;
}
