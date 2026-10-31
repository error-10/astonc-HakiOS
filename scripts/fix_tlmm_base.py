# 修 Wi-Fi 探针里的 TLMM 基址：0xF100000 是错的，真机设备树里是 pinctrl@f000000。
# 结果：以前 perst/clkreq/wlan-en 的写全部落在高 0x100000 处（相当于错开到别的
# GPIO 号上），读回自然是 0，PERST 从来没真正释放过。
import sys

p = r'C:\Users\96943\Desktop\ios\port\kernel\hakios.aston_wifi.c'
t = open(p, encoding='utf-8').read()

old = '#define ASTON_TLMM            0x0f100000ul      /* dt: pinctrl@f100000 */'
new = ('#define ASTON_TLMM            0x0f000000ul      /* dt: pinctrl@f000000.\n'
       '                                                    * Was 0xf100000: every pin write landed one\n'
       '                                                    * megabyte too high, so PERST was never released. */')
if old not in t:
    print('constant line not found - already patched?')
    sys.exit(1)
t = t.replace(old, new)
t = t.replace('*             and the perst / clkreq / wlan-en pins at 0xf100000: whether the controller is',
              '*             and the perst / clkreq / wlan-en pins at 0xf000000: whether the controller is')
open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('patched', p)
