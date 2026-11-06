#pragma once

#include "cuda_runtime_api.h"

/**
 * @defgroup apis_for_cuda
 * @brief APIs for CUDA.
 * @{
 */
/**
 * @brief Launch application to remote chiplet.
 * @param __dst_x Destination address in X-axis.
 * @param __dst_y Destination address in Y-axis.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 */
extern __host__ cudaError_t CUDARTAPI launch(int __dst_x, int __dst_y, int __src_x, int __src_y);

/**
 * @brief Wait launch from remote chiplet.
 * @param __dst_x Destination address in X-axis.
 * @param __dst_y Destination address in Y-axis.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 */
extern __host__ cudaError_t CUDARTAPI waitLaunch(int __dst_x, int __dst_y, int* __src_x,
                                                 int* __src_y);

/**
 * @brief Barrier.
 * @param __uid Barrier ID.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 * @param __count Number of threads to barrier. 
 */
extern __host__ cudaError_t CUDARTAPI barrier(int __uid, int __src_x, int __src_y, int __count = 0);

/**
 * @brief Lock mutex.
 * @param __uid Mutex ID.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 */
extern __host__ cudaError_t CUDARTAPI lock(int __uid, int __src_x, int __src_y);

/**
 * @brief Unlock mutex.
 * @param __uid Mutex ID.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 */
extern __host__ cudaError_t CUDARTAPI unlock(int __uid, int __src_x, int __src_y);

/**
 * @brief Send data to remote chiplet.
 * @param __dst_x Destination address in X-axis.
 * @param __dst_y Destination address in Y-axis.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 * @param __addr Data address.
 * @param __nbyte Number of bytes.
 */
extern __host__ cudaError_t CUDARTAPI sendMessage(int __dst_x, int __dst_y, int __src_x,
                                                  int __srx_y, void* __addr, int __nbyte);

/**
 * @brief Read data from remote chiplet.
 * @param __dst_x Destination address in X-axis.
 * @param __dst_y Destination address in Y-axis.
 * @param __src_x Source address in X-axis.
 * @param __src_y Source address in Y-axis.
 * @param __addr Data address.
 * @param __nbyte Number of bytes.
 */
extern __host__ cudaError_t CUDARTAPI receiveMessage(int __dst_x, int __dst_y, int __src_x,
                                                     int __srx_y, void* __addr, int __nbyte);

/**
 * @brief Send data to remote sub chiplet.
 * @param __main_xy Main process address in X-axis and Y-axis.
 * @param __sub_xy Sub process address in X-axis and Y-axis.
 * @param __addr Data address.
 * @param __nbyte Number of bytes.
 * @param __dest_addr Data address in sub process.
 */
extern __host__ cudaError_t CUDARTAPI sendSubMessage(int __main_xy, int __sub_xy,
                                                     void* __addr, int __nbyte, uint64_t __dest_addr);
/**
 * @brief Read data from remote sub chiplet.
 * @param __main_xy Main process address in X-axis and Y-axis.
 * @param __sub_xy Sub process address in X-axis and Y-axis.
 * @param __addr Data address.
 * @param __nbyte Number of bytes.
 * @param __dest_addr Data address in sub process.
 */
extern __host__ cudaError_t CUDARTAPI receiveSubMessage(int __main_xy, int __sub_xy,
                                                        void* __addr, int __nbyte, uint64_t __dest_addr);

/**
 * @brief End remote sub chiplet.
 * @param __main_xy Main process address in X-axis and Y-axis.
 * @param __sub_xy Sub process address in X-axis and Y-axis.
 */
extern __host__ cudaError_t CUDARTAPI endSubMessage(int __main_xy, int __sub_xy);

/**
 * @}
 */