ifeq ($(HOST),armv7a-linux-android)
android_AR=$(ANDROID_TOOLCHAIN_BIN)/llvm-ar
android_CXX=$(ANDROID_TOOLCHAIN_BIN)/$(HOST)eabi$(ANDROID_API_LEVEL)-clang++
android_CC=$(ANDROID_TOOLCHAIN_BIN)/$(HOST)eabi$(ANDROID_API_LEVEL)-clang
android_RANLIB=$(ANDROID_TOOLCHAIN_BIN)/llvm-ranlib
else
android_AR=$(ANDROID_TOOLCHAIN_BIN)/llvm-ar
android_CXX=$(ANDROID_TOOLCHAIN_BIN)/$(HOST)$(ANDROID_API_LEVEL)-clang++
android_CC=$(ANDROID_TOOLCHAIN_BIN)/$(HOST)$(ANDROID_API_LEVEL)-clang
android_RANLIB=$(ANDROID_TOOLCHAIN_BIN)/llvm-ranlib
endif
android_CXXFLAGS=-DBOOST_NO_CXX98_FUNCTION_BASE -D_HAS_AUTO_PTR_ETC=0 -Wno-enum-constexpr-conversion
android_cmake_system=Android
