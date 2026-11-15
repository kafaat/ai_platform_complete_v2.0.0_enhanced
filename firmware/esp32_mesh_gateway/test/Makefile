# Host test of cmd_auth_v2.h against the Python-generated vectors (g++ + OpenSSL).
#   make -C firmware/esp32_mesh_gateway/test          # build + run
#   make -C firmware/esp32_mesh_gateway/test clean
# The binary is written outside the source tree (BUILD_DIR, default /tmp) so a run never
# leaves an artefact in the checkout.
CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O1
BUILD_DIR ?= /tmp/sahool-cmd-auth-v2-test
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: test clean
test: $(BUILD_DIR)/test_cmd_auth_v2
	$(BUILD_DIR)/test_cmd_auth_v2 $(HERE)cmd_auth_v2_vectors.json

$(BUILD_DIR)/test_cmd_auth_v2: $(HERE)test_cmd_auth_v2.cpp $(HERE)../cmd_auth_v2.h
	mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $(HERE)test_cmd_auth_v2.cpp -lcrypto

clean:
	rm -rf $(BUILD_DIR)
