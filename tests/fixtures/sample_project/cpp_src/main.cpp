#include <iostream>
#include "handler.h"

namespace app {

class Application {
public:
    Application();
    void run();
private:
    int _status;
};

Application::Application() : _status(0) {}

void Application::run() {
    std::cout << "running" << std::endl;
}

}  // namespace app

int main() {
    app::Application a;
    a.run();
    return 0;
}
