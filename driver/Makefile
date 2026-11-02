# SPDX-License-Identifier: GPL-2.0
# Jetson Linux R36.4.7 external-module build. Uses installed NVIDIA headers.
KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build
NVROOT ?= /usr/src/nvidia/nvidia-oot
obj-m := ov5647.o
ccflags-y += -I$(NVROOT)/include

.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) KBUILD_EXTRA_SYMBOLS="$(NVROOT)/Module.symvers" modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
