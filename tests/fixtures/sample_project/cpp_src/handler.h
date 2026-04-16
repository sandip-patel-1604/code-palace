#pragma once
#include <string>
#include <vector>

namespace app {

struct Config {
    int port;
    std::string host;
};

class Handler {
public:
    Handler(const Config& cfg);
    void handle(const std::string& request);
    std::string status() const;
private:
    Config _config;
};

enum Status { OK = 0, ERROR = 1, PENDING = 2 };

template<typename T>
T identity(T val) { return val; }

const int MAX_CONNECTIONS = 100;

}  // namespace app
