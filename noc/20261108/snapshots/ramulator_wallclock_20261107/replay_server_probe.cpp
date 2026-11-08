// Reuse only the independently written direct-engine test reference, not any
// candidate wrapper service. Renaming its standalone test entry avoids a
// second main; its artificial test function is not called here.
#define main unused_standalone_clock_test_entry
#include "clock_probe.cpp"
#undef main
#include <sstream>
#include <vector>

int main(int argc,char**argv){
    try{
        if(argc!=3)throw std::runtime_error("config joined_actual_server_csv required");
        DirectReference reference(argv[1]);std::ifstream f(argv[2]);std::string line;
        std::getline(f,line);std::size_t count=0;
        while(std::getline(f,line)){
            std::replace(line.begin(),line.end(),',',' ');std::istringstream row(line);
            std::uint64_t arrival,address,bytes,start,end,done;int write;
            if(!(row>>arrival>>address>>bytes>>write>>start>>end>>done))throw std::runtime_error("bad joined real server record");
            auto expected=reference.submit(write,address,bytes,arrival);
            if(expected.first!=start||expected.second!=end||(end*5+3)/4!=done)
                throw std::runtime_error("actual server diverges from direct native engine at record "+std::to_string(count));
            ++count;
        }
        if(count!=12)throw std::runtime_error("expected all 12 real server transactions");
        std::cout<<"PASS actual native-server clock against independent engine: "<<count<<" requests\n";
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
