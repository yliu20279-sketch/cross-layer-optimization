#pragma once
// Isolated test adapter: preserve complete protocol lines across read() calls.
// Command decoding remains the original SDK's parseCmd(std::string).
#include <cerrno>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <unistd.h>

class LineReceiver {
    int fd_;
    std::size_t chunk_;
    std::string pending_;
public:
    explicit LineReceiver(int fd, std::size_t chunk=4096):fd_(fd),chunk_(chunk) {
        if(chunk_==0 || chunk_>4096)throw std::runtime_error("invalid read chunk");
    }
    std::string next() {
        for(;;) {
            const auto p=pending_.find('\n');
            if(p!=std::string::npos) {
                auto line=pending_.substr(0,p+1);pending_.erase(0,p+1);return line;
            }
            if(pending_.size()>65536)throw std::runtime_error("oversize protocol line");
            char data[4096];const auto n=::read(fd_,data,chunk_);
            if(n<0) {if(errno==EINTR)continue;throw std::runtime_error("response read failed");}
            if(n==0)throw std::runtime_error(pending_.empty()?"response EOF":"incomplete response at EOF");
            pending_.append(data,static_cast<std::size_t>(n));
        }
    }
};
