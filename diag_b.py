from scope_oracle import resolver as r
aud = ("COUNT = 0\n\ndef total(items):\n    global COUNT\n"
       "    COUNT = COUNT + 1\n    return len(items) + COUNT\n")
rev = ("COUNT = 0\n\ndef total(items):\n    global COUNT\n"
       "    return len(items) + COUNT\n")
b, v = r.check(aud, "b"), r.check(rev, "v")
print("RESOLVER_ID:", r.RESOLVER_ID)
print("BASE health:", b)
print("VAR  health:", v)
print("W2 fires (newly_broken):", r.newly_broken(b, v))