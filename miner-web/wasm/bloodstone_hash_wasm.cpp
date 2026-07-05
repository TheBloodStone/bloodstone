// WASM wrapper matching spacexpanse-hash / stratum validation.
#include <cstring>
#include <string>
#include <vector>

#include <core_io.h>
#include <powdata.h>
#include <primitives/pureheader.h>
#include <uint256.h>

#include <emscripten.h>

extern "C" {

EMSCRIPTEN_KEEPALIVE
int bloodstone_neoscrypt_hash(const char *header_hex, char *out_hex, int out_size) {
  if (out_hex == nullptr || out_size < 65) {
    return -1;
  }

  CPureBlockHeader header;
  if (!DecodeHexPureHeader(header, std::string(header_hex))) {
    return -2;
  }

  try {
    const uint256 hash = header.GetPowHash(PowAlgo::NEOSCRYPT);
    const std::string hex = hash.GetHex();
    if (static_cast<int>(hex.size()) + 1 > out_size) {
      return -3;
    }
    std::memcpy(out_hex, hex.c_str(), hex.size() + 1);
    return 0;
  } catch (...) {
    return -4;
  }
}

EMSCRIPTEN_KEEPALIVE
int bloodstone_yespower_hash(const char *header_hex, char *out_hex, int out_size) {
  if (out_hex == nullptr || out_size < 65) {
    return -1;
  }

  CPureBlockHeader header;
  if (!DecodeHexPureHeader(header, std::string(header_hex))) {
    return -2;
  }

  try {
    const uint256 hash = header.GetPowHash(PowAlgo::YESPOWER);
    const std::string hex = hash.GetHex();
    if (static_cast<int>(hex.size()) + 1 > out_size) {
      return -3;
    }
    std::memcpy(out_hex, hex.c_str(), hex.size() + 1);
    return 0;
  } catch (...) {
    return -4;
  }
}

}  // extern "C"