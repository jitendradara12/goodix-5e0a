# Tier 4: rescoped

Application-scenario sequencing with MockGoodixMCU was removed (197-line
suite deleted in 703950a). Tier 4 now covers only offline resource-sampler
fixtures (`test_resource_sampler.py`); it asserts nothing about live
fprintd cost. MockGoodixMCU consumers remain in Tier 5.
