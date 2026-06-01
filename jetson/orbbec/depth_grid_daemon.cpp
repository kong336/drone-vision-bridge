#include "libobsensor/ObSensor.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

static std::atomic<bool> g_running(true);

static void handle_signal(int) {
    g_running = false;
}

static int arg_int(int argc, char **argv, int index, int fallback) {
    if(argc <= index) {
        return fallback;
    }
    int value = std::atoi(argv[index]);
    return value > 0 ? value : fallback;
}

static double now_seconds() {
    using clock = std::chrono::system_clock;
    auto now = clock::now().time_since_epoch();
    return std::chrono::duration<double>(now).count();
}

int main(int argc, char **argv) try {
    std::string out_path = argc > 1 ? argv[1] : "/tmp/orbbec_depth_grid.json";
    int grid_w = arg_int(argc, argv, 2, 32);
    int grid_h = arg_int(argc, argv, 3, 20);
    int write_every_ms = arg_int(argc, argv, 4, 100);

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    ob::Pipeline pipe;
    auto config = std::make_shared<ob::Config>();
    config->enableVideoStream(OB_STREAM_DEPTH);
    pipe.start(config);

    std::vector<double> sums(grid_w * grid_h);
    std::vector<int> counts(grid_w * grid_h);
    std::vector<double> grid_mm(grid_w * grid_h);
    auto last_write = std::chrono::steady_clock::now() - std::chrono::milliseconds(write_every_ms);

    while(g_running) {
        auto frameSet = pipe.waitForFrames(1000);
        if(!frameSet) {
            continue;
        }
        auto depthFrame = frameSet->depthFrame();
        if(!depthFrame || depthFrame->format() != OB_FORMAT_Y16) {
            continue;
        }
        auto current_time = std::chrono::steady_clock::now();
        if(std::chrono::duration_cast<std::chrono::milliseconds>(current_time - last_write).count() < write_every_ms) {
            continue;
        }
        last_write = current_time;

        int width = static_cast<int>(depthFrame->width());
        int height = static_cast<int>(depthFrame->height());
        float scale = depthFrame->getValueScale();
        auto *data = static_cast<uint16_t *>(depthFrame->data());

        std::fill(sums.begin(), sums.end(), 0.0);
        std::fill(counts.begin(), counts.end(), 0);

        for(int y = 0; y < height; ++y) {
            int gy = std::min(grid_h - 1, y * grid_h / height);
            for(int x = 0; x < width; ++x) {
                uint16_t raw = data[y * width + x];
                if(raw == 0) {
                    continue;
                }
                int gx = std::min(grid_w - 1, x * grid_w / width);
                int idx = gy * grid_w + gx;
                sums[idx] += static_cast<double>(raw) * scale;
                counts[idx] += 1;
            }
        }

        int valid_cells = 0;
        int valid_pixels = 0;
        double full_sum = 0.0;
        for(int i = 0; i < grid_w * grid_h; ++i) {
            if(counts[i] > 0) {
                grid_mm[i] = sums[i] / counts[i];
                valid_cells += 1;
                valid_pixels += counts[i];
                full_sum += sums[i];
            }
            else {
                grid_mm[i] = 0.0;
            }
        }

        std::ostringstream json;
        json.setf(std::ios::fixed);
        json.precision(3);
        json << "{";
        json << "\"ok\":" << (valid_pixels > 0 ? "true" : "false");
        json << ",\"status\":\"" << (valid_pixels > 0 ? "ok" : "no_valid_depth") << "\"";
        json << ",\"timestamp\":" << now_seconds();
        json << ",\"width\":" << width;
        json << ",\"height\":" << height;
        json << ",\"grid_w\":" << grid_w;
        json << ",\"grid_h\":" << grid_h;
        json << ",\"scale\":" << scale;
        json << ",\"valid_cells\":" << valid_cells;
        json << ",\"valid_pixels\":" << valid_pixels;
        if(valid_pixels > 0) {
            json << ",\"full_avg_mm\":" << (full_sum / valid_pixels);
        }
        json << ",\"grid_mm\":[";
        for(int i = 0; i < grid_w * grid_h; ++i) {
            if(i) {
                json << ",";
            }
            json << grid_mm[i];
        }
        json << "]}";

        std::string tmp_path = out_path + ".tmp";
        {
            std::ofstream out(tmp_path, std::ios::trunc);
            out << json.str() << "\n";
        }
        std::rename(tmp_path.c_str(), out_path.c_str());
    }

    pipe.stop();
    return 0;
}
catch(ob::Error &e) {
    std::cerr << "{\"ok\":false,\"error\":\"orbbec\",\"function\":\"" << e.getName()
              << "\",\"message\":\"" << e.getMessage() << "\"}" << std::endl;
    return 1;
}
