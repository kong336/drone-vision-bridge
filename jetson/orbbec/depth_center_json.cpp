#include "libobsensor/ObSensor.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <numeric>
#include <thread>
#include <vector>

int main(int argc, char **argv) try {
    int samples = 30;
    if(argc > 1) {
        samples = std::max(1, std::atoi(argv[1]));
    }

    ob::Pipeline pipe;
    auto config = std::make_shared<ob::Config>();
    config->enableVideoStream(OB_STREAM_DEPTH);
    pipe.start(config);

    std::vector<double> center_roi_mm;
    double full_sum_mm = 0.0;
    int full_valid = 0;
    int width = 0;
    int height = 0;
    float scale = 0.0f;

    for(int i = 0; i < samples; ++i) {
        auto frameSet = pipe.waitForFrames(1000);
        if(!frameSet) {
            continue;
        }
        auto depthFrame = frameSet->depthFrame();
        if(!depthFrame || depthFrame->format() != OB_FORMAT_Y16) {
            continue;
        }

        width = static_cast<int>(depthFrame->width());
        height = static_cast<int>(depthFrame->height());
        scale = depthFrame->getValueScale();
        auto *data = static_cast<uint16_t *>(depthFrame->data());
        int cx = width / 2;
        int cy = height / 2;
        int radius = 8;
        for(int y = std::max(0, cy - radius); y <= std::min(height - 1, cy + radius); ++y) {
            for(int x = std::max(0, cx - radius); x <= std::min(width - 1, cx + radius); ++x) {
                auto raw = data[y * width + x];
                if(raw != 0) {
                    center_roi_mm.push_back(static_cast<double>(raw) * scale);
                }
            }
        }
        for(int idx = 0; idx < width * height; ++idx) {
            auto raw = data[idx];
            if(raw != 0) {
                full_sum_mm += static_cast<double>(raw) * scale;
                full_valid += 1;
            }
        }
    }

    pipe.stop();

    std::sort(center_roi_mm.begin(), center_roi_mm.end());

    std::cout << "{";
    std::cout << "\"ok\":" << (!center_roi_mm.empty() || full_valid > 0 ? "true" : "false");
    std::cout << ",\"samples\":" << samples;
    std::cout << ",\"center_roi_valid_pixels\":" << center_roi_mm.size();
    std::cout << ",\"full_valid_pixels\":" << full_valid;
    std::cout << ",\"width\":" << width;
    std::cout << ",\"height\":" << height;
    std::cout << ",\"scale\":" << scale;
    if(!center_roi_mm.empty()) {
        auto distance_mm = center_roi_mm[center_roi_mm.size() / 2];
        std::cout << ",\"center_roi_median_mm\":" << distance_mm;
        std::cout << ",\"center_distance_m\":" << (distance_mm / 1000.0);
    }
    if(full_valid > 0) {
        auto full_avg_mm = full_sum_mm / full_valid;
        std::cout << ",\"full_avg_mm\":" << full_avg_mm;
    }
    std::cout << "}" << std::endl;

    return (!center_roi_mm.empty() || full_valid > 0) ? 0 : 2;
}
catch(ob::Error &e) {
    std::cerr << "{";
    std::cerr << "\"ok\":false";
    std::cerr << ",\"error\":\"orbbec\"";
    std::cerr << ",\"function\":\"" << e.getName() << "\"";
    std::cerr << ",\"message\":\"" << e.getMessage() << "\"";
    std::cerr << "}" << std::endl;
    return 1;
}
