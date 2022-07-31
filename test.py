def dec_cc101_freq(mhz):
    def subf(div):
        nonlocal mhz
        resf = int(mhz // div)
        mhz -= resf * div
        return resf

    f0 = subf(26)
    f1 = subf(0.1015625)
    f2 = subf(0.00039675)

    print("%02x %02x %02x" % (f0, f1, f2))

dec_cc101_freq(433.92)
