When adding new features, keep the simulation-first approach.

Add new sensors/actuators by:
1) extending `espresso_mod/hal/base.py` protocols (if needed)
2) adding a simulation implementation in `espresso_mod/hal/sim.py`
3) adding API endpoints that call services, not HAL directly
4) adding tests

Avoid mixing hardware imports into modules that run on dev machines.
