// Copyright (c) 2026 The Bloodstone developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_CRYPTO_YESPOWERR16_H
#define BITCOIN_CRYPTO_YESPOWERR16_H

#include <uint256.h>

#include <vector>

/** yespower 1.0 with N=4096, r=16, empty personalization (yespowerr16). */
uint256 YespowerR16Hash(const std::vector<unsigned char>& data);

#endif // BITCOIN_CRYPTO_YESPOWERR16_H