cmake_minimum_required(VERSION 3.20)
project(SentinelStatArbEngine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_library(sentinel_core STATIC src/execution_engine.cpp)
target_include_directories(sentinel_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include ${CMAKE_SOURCE_DIR}/vendor)
target_compile_options(sentinel_core PRIVATE -O3 -Wall -Wextra -Wpedantic)

find_package(Threads REQUIRED)

add_executable(sentinel_spsc_bench src/spsc_bench.cpp)
target_link_libraries(sentinel_spsc_bench PRIVATE sentinel_core Threads::Threads)
target_include_directories(sentinel_spsc_bench PRIVATE ${CMAKE_SOURCE_DIR}/vendor)
target_compile_options(sentinel_spsc_bench PRIVATE -O3 -march=native)

add_executable(sentinel_engine_smoke src/engine_smoke.cpp)
target_link_libraries(sentinel_engine_smoke PRIVATE sentinel_core)
target_compile_options(sentinel_engine_smoke PRIVATE -O2 -Wall -Wextra -Wpedantic)

find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(LIBZMQ QUIET libzmq)
endif()

if(LIBZMQ_FOUND)
  add_executable(sentinel_exec src/sentinel_exec.cpp)
  target_include_directories(sentinel_exec PRIVATE ${LIBZMQ_INCLUDE_DIRS})
  target_link_directories(sentinel_exec PRIVATE ${LIBZMQ_LIBRARY_DIRS})
  target_link_libraries(sentinel_exec PRIVATE sentinel_core ${LIBZMQ_LIBRARIES})
  target_compile_options(sentinel_exec PRIVATE ${LIBZMQ_CFLAGS_OTHER} -O3 -march=native)

  add_executable(sentinel_zmq_bench src/zmq_latency_bench.cpp)
  target_include_directories(sentinel_zmq_bench PRIVATE ${LIBZMQ_INCLUDE_DIRS})
  target_link_directories(sentinel_zmq_bench PRIVATE ${LIBZMQ_LIBRARY_DIRS})
  target_link_libraries(sentinel_zmq_bench PRIVATE ${LIBZMQ_LIBRARIES})
  target_compile_options(sentinel_zmq_bench PRIVATE ${LIBZMQ_CFLAGS_OTHER} -O3 -march=native)

  add_test(NAME sentinel_zmq_bench COMMAND sentinel_zmq_bench 1000)
else()
  message(WARNING "libzmq development headers not found; ZeroMQ targets/tests are skipped")
endif()

add_test(NAME sentinel_spsc_bench COMMAND sentinel_spsc_bench)
add_test(NAME sentinel_engine_smoke COMMAND sentinel_engine_smoke)
