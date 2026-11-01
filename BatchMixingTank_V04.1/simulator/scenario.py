"""Approved scenario F1-F10 (chat 01.11.2026)."""
SCENARIO = {
    'typed': {                     # operator typed volumes: (volume, dialog answer)
        '0003.0': [(50, 'confirm')],                          # F1
        '0005.0': [(110, None), (90, 'cancel'), (100, None)],  # F2
    },
    'faults': {
        'F3': dict(batch='0007.0', kind='flow', product=1, factor=1.10,
                   desc='IN_P1 flow +10 % during the Prd_1 dose'),
        'F4': dict(batch='0013.0', kind='flow', product=3, factor=1.20,
                   desc='IN_P3 flow +20 % on the last dose of a 100 L batch'),
        'F5': dict(batch='0020.0', kind='noflow', product=2, repair_s=60,
                   desc='IN_P2 no flow; repaired 60 s after the alarm'),
        'F6': dict(batch='0022.0', kind='stuck_open', valve='IN_CLEAN', substep=4,
                   desc='IN_CLEAN stuck open during the drain of the pre-batch cleaning'),
        'F7': dict(batch='0026.1', kind='estop_empty', frac=0.5,
                   desc='Operator Emergency Stop at 50 % of Emptying'),
        'F8': dict(batch='0024.0', kind='estop_waiting',
                   desc='Operator Emergency Stop in Waiting'),
        'F9': dict(batch='0017.1', kind='stop_mixing', frac=0.5,
                   desc='Operator Normal Stop during Mixing'),
        'F10': dict(batch='0029.0', kind='stop_preclean', substep=3, frac=0.5,
                    desc='Operator Normal Stop during the pre-batch cleaning (mix step)'),
    },
}
