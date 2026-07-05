#include <stdint.h>
#include <emscripten.h>
#include "neoscrypt.h"

EMSCRIPTEN_KEEPALIVE
void neoscrypt_hash(const uint8_t *input, uint8_t *output) {
    neoscrypt(input, output, 0);
}
