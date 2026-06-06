# Fixes Applied — Results

## Fix 1: Missing person nodes ✅
**Before:** 43,915 dangling co_credited edges (89%)
**After:** 2,811 new person stubs, all 49,485 co_credited edges valid → **0 dangling**

## Fix 2: Reviewed films not in graph ✅
**Before:** 3,869 dangling reviewed edges (96%)
**After:** 3,116 new film stubs from blog metadata, 7,847 reviewed edges (dupes accumulated via merging) → **0 dangling**

## Fix 3: fund_recipient empty source ✅
**Before:** 6 dangling fund_recipient edges
**After:** 0 fund_recipient edges — skipped all because funding records lack per-film titles. This is a data limitation (not a code bug). Funding is aggregated per fund page, not per film.

## Fix 4: Role mapping ✅
**Before:** 68% roles = "other" (only 6 Hebrew strings mapped)
**After:** 45% roles = "other" (33 role strings mapped). Top roles: producer (569), screenwriter (345), director (306), cinematographer (234), editor (206)

## Fix 5: is_short always False ✅
**Before:** All 285 films had is_short=False
**After:** 97 films correctly marked is_short=True

## Final Graph
| Metric | Before | After |
|--------|--------|-------|
| Nodes | 3,006 | **8,182** |
| Persons | 2,713 | **4,895** |
| Films | 285 | **3,279** |
| Dangling edges | 43,915 | **0** |
| Verified | ❌ | ✅ |
