cmake_minimum_required(VERSION 3.16)
project(perp_bot CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug)
endif()

add_compile_options(-Wall -Wextra -Wpedantic -Werror)

find_package(Threads REQUIRED)

add_library(perpcore STATIC
    src/config.cpp
    src/signal.cpp
    src/risk.cpp
    src/position_manager.cpp
    src/exchange.cpp
    src/bot.cpp
    src/backtest.cpp
    src/sweep.cpp
    src/validate.cpp
    src/panel.cpp
    src/mm.cpp
)
target_link_libraries(perpcore PUBLIC Threads::Threads)
target_include_directories(perpcore PUBLIC include)

foreach(exe perp_backtest perp_sweep perp_validate perp_panel perp_mm)
    add_executable(${exe} src/${exe}.cpp)
    target_link_libraries(${exe} PRIVATE perpcore)
endforeach()

# Tests assert-based (pas de GoogleTest), lancés par ctest.
enable_testing()
foreach(t types exchange risk position_manager signal config backtest sweep validate panel direction mm)
    add_executable(test_${t} tests/test_${t}.cpp)
    target_link_libraries(test_${t} PRIVATE perpcore)
    target_compile_definitions(test_${t} PRIVATE PERP_SOURCE_DIR="${CMAKE_SOURCE_DIR}")
    add_test(NAME test_${t} COMMAND test_${t})
endforeach()

find_program(PYTHON_EXE NAMES python python3)
if (PYTHON_EXE)
    add_test(NAME test_recorder COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_recorder.py)
    add_test(NAME test_premium_study COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_premium_study.py)
    add_test(NAME test_leadlag_study COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_leadlag_study.py)
    add_test(NAME test_tsmom_study COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_tsmom_study.py)
    add_test(NAME test_fetch_trades COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_fetch_trades.py)
    add_test(NAME test_mm_economics COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_mm_economics.py)
    add_test(NAME test_grid_stage1 COMMAND ${PYTHON_EXE} ${CMAKE_SOURCE_DIR}/tests/test_grid_stage1.py)
endif()
