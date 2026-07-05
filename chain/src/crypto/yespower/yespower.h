/* Standalone yespower header for Bloodstone (adapted from cpuminer-opt / yespower 1.0). */
#ifndef BLOODSTONE_YESPOWER_H
#define BLOODSTONE_YESPOWER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum { YESPOWER_0_5 = 5, YESPOWER_1_0 = 10 } yespower_version_t;

typedef struct {
	yespower_version_t version;
	uint32_t N, r;
	const uint8_t *pers;
	size_t perslen;
} yespower_params_t;

typedef struct {
	unsigned char uc[32];
} yespower_binary_t;

typedef struct {
	void *base, *aligned;
	size_t base_size, aligned_size;
} yespower_local_t;

extern int yespower_init_local(yespower_local_t *local);
extern int yespower_free_local(yespower_local_t *local);
extern int yespower_tls(const uint8_t *src, size_t srclen,
                        const yespower_params_t *params, yespower_binary_t *dst);

#ifdef __cplusplus
}
#endif

#endif /* BLOODSTONE_YESPOWER_H */