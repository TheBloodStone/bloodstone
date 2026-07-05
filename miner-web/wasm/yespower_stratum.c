#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <emscripten.h>
#include "yespower.h"

static void swap_getwork(uint8_t *data, size_t len) {
    for (size_t i = 0; i + 3 < len; i += 4) {
        uint8_t t0 = data[i];
        uint8_t t1 = data[i + 1];
        data[i] = data[i + 3];
        data[i + 3] = t0;
        data[i + 1] = data[i + 2];
        data[i + 2] = t1;
    }
}

/* Canonical 80-byte header in; same PoW path as bloodstone-hash / GetPowHash. */
EMSCRIPTEN_KEEPALIVE
int yespower_stratum_hash(const uint8_t *header, char *out_hex, int out_size) {
    if (out_hex == NULL || out_size < 65) {
        return -1;
    }

    uint8_t buf[80];
    memcpy(buf, header, 80);
    swap_getwork(buf, 80);

    static const yespower_params_t params = {
        YESPOWER_1_0,
        4096,
        16,
        NULL,
        0,
    };

    yespower_binary_t result;
    if (yespower_tls_ref(buf, 80, &params, &result, 0) != 1) {
        return -2;
    }

    for (int i = 0; i < 32; ++i) {
        sprintf(out_hex + i * 2, "%02x", result.uc[31 - i]);
    }
    out_hex[64] = '\0';
    return 0;
}