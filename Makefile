# Else exist specifically for clang
ifeq ($(CXX),g++)
    EXTRA_FLAGS = --no-gnu-unique
else
    EXTRA_FLAGS =
endif

CXXFLAGS ?= -O2
CXXFLAGS += -shared -fPIC -std=c++2b

all:
	$(CXX) $(CXXFLAGS) $(LDFLAGS) $(EXTRA_FLAGS) main.cpp borderDeco.cpp BorderppPassElement.cpp svgSlices.cpp -o borders-plus-plus-svg.so.tmp `pkg-config --cflags pixman-1 libdrm hyprland pangocairo libinput libudev wayland-server xkbcommon librsvg-2.0` `pkg-config --libs librsvg-2.0`
	# replace rather than overwrite, a running Hyprland may have the old one mapped
	mv -f borders-plus-plus-svg.so.tmp borders-plus-plus-svg.so

clean:
	rm ./borders-plus-plus-svg.so
