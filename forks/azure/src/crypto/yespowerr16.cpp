// Copyright (c) 2026 The Bloodstone developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/yespowerr16.h>

#include <crypto/yespower/yespower.h>

#include <cstring>

uint256 YespowerR16Hash(const std::vector<unsigned char>& data)
{
    static const yespower_params_t params = {
        YESPOWER_1_0,
        4096,
        16,
        nullptr,
        0,
    };

    yespower_local_t local;
    if (yespower_init_local(&local) != 0) {
        return uint256();
    }

    yespower_binary_t result;
    if (yespower_tls(data.data(), data.size(), &params, &result) != 0) {
        yespower_free_local(&local);
        return uint256();
    }
    yespower_free_local(&local);

    uint256 hash;
    for (size_t i = 0; i < hash.size(); ++i) {
        hash.begin()[i] = result.uc[hash.size() - 1 - i];
    }
    return hash;
}