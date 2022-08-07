def log(level, *args):
    """
    Levels are:
     0 = critical (crashes the program)
     1 = error (causes operation to fail)
     2 = warning (encountered unknown scenarios)
     3 = info (what's going on at a glance)
     4+ = debug
    """
    # for now does nothing but print
    print(*args)
