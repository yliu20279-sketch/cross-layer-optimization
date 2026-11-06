#pragma once
#include <stdexcept>
#define LOG_ASSERT_ERROR(c,m) do{if(!(c))throw std::runtime_error(m);}while(0)
