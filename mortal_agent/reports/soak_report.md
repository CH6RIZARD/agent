# Soak Test Report

## Summary
- Total sessions: 35
- Total turns: 119
- Doc usage (overall): 16/119 = 13.45%
- Identity spam (unprompted boilerplate): 0
- Repetition score (0–1): 0.130

## Acceptance Checks
- Doc usage in 25–45%: **FAIL** (13.45%)
- Identity spam near 0: **PASS** (0)
- Repetition low: **PASS** (0.130)

## Doc Usage Per Session

- identity_1 (identity_probing): 16.67%
- identity_2 (identity_probing): 0.00%
- identity_3 (identity_probing): 0.00%
- god_1 (who_is_god): 33.33%
- god_2 (who_is_god): 33.33%
- god_3 (who_is_god): 66.67%
- build_1 (practical_build): 33.33%
- build_2 (practical_build): 33.33%
- build_3 (practical_build): 33.33%
- build_4 (practical_build): 33.33%
- build_5 (practical_build): 33.33%
- build_6 (practical_build): 33.33%
- build_7 (practical_build): 33.33%
- build_8 (practical_build): 0.00%
- debate_1 (debate): 0.00%
- debate_2 (debate): 0.00%
- debate_3 (debate): 0.00%
- debate_4 (debate): 0.00%
- creative_1 (creative): 0.00%
- creative_2 (creative): 0.00%
- creative_3 (creative): 0.00%
- creative_4 (creative): 0.00%
- creative_5 (creative): 0.00%
- creative_6 (creative): 0.00%
- debug_1 (troubleshooting): 0.00%
- debug_2 (troubleshooting): 0.00%
- debug_3 (troubleshooting): 33.33%
- debug_4 (troubleshooting): 33.33%
- debug_5 (troubleshooting): 0.00%
- debug_6 (troubleshooting): 33.33%
- ethical_1 (ethical_boundary): 0.00%
- ethical_2 (ethical_boundary): 0.00%
- meta_1 (meta_constraints): 0.00%
- meta_2 (meta_constraints): 0.00%
- meta_3 (meta_constraints): 0.00%

## Identity Spam Per Session

- identity_1: 0
- identity_2: 0
- identity_3: 0
- god_1: 0
- god_2: 0
- god_3: 0
- build_1: 0
- build_2: 0
- build_3: 0
- build_4: 0
- build_5: 0
- build_6: 0
- build_7: 0
- build_8: 0
- debate_1: 0
- debate_2: 0
- debate_3: 0
- debate_4: 0
- creative_1: 0
- creative_2: 0
- creative_3: 0
- creative_4: 0
- creative_5: 0
- creative_6: 0
- debug_1: 0
- debug_2: 0
- debug_3: 0
- debug_4: 0
- debug_5: 0
- debug_6: 0
- ethical_1: 0
- ethical_2: 0
- meta_1: 0
- meta_2: 0
- meta_3: 0

## Coherence Flags

None

## Human Voice Heuristics (sample)

- Session 0: {'length_std': 70.83882331665941, 'all_same_length': False, 'bullet_heavy': False}
- Session 1: {'length_std': 102.30425211104375, 'all_same_length': False, 'bullet_heavy': False}
- Session 2: {'length_std': 102.3202814695112, 'all_same_length': False, 'bullet_heavy': False}
- Session 3: {'length_std': 26.948510575210314, 'all_same_length': False, 'bullet_heavy': False}
- Session 4: {'length_std': 163.27141683575712, 'all_same_length': False, 'bullet_heavy': False}

## Failure List

- identity_1 (identity_probing): doc_used log length 5 != turns 6
- identity_2 (identity_probing): doc_used log length 4 != turns 5
- identity_3 (identity_probing): doc_used log length 2 != turns 5
- god_1 (who_is_god): doc_used log length 1 != turns 3
- god_2 (who_is_god): doc_used log length 1 != turns 3
- build_1 (practical_build): doc_used log length 4 != turns 6
- build_2 (practical_build): doc_used log length 1 != turns 3
- build_3 (practical_build): doc_used log length 1 != turns 3
- build_4 (practical_build): doc_used log length 2 != turns 3
- build_5 (practical_build): doc_used log length 1 != turns 3
- build_6 (practical_build): doc_used log length 2 != turns 3
- build_7 (practical_build): doc_used log length 2 != turns 3
- build_8 (practical_build): doc_used log length 2 != turns 3
- debate_1 (debate): doc_used log length 2 != turns 4
- debate_2 (debate): doc_used log length 2 != turns 4
- debate_3 (debate): doc_used log length 1 != turns 4
- debate_4 (debate): doc_used log length 3 != turns 4
- creative_1 (creative): doc_used log length 1 != turns 3
- creative_2 (creative): doc_used log length 2 != turns 3
- creative_3 (creative): doc_used log length 1 != turns 3
- creative_4 (creative): doc_used log length 1 != turns 3
- creative_5 (creative): doc_used log length 2 != turns 3
- creative_6 (creative): doc_used log length 2 != turns 3
- debug_1 (troubleshooting): doc_used log length 2 != turns 3
- debug_2 (troubleshooting): doc_used log length 1 != turns 3
- debug_3 (troubleshooting): doc_used log length 2 != turns 3
- debug_4 (troubleshooting): doc_used log length 1 != turns 3
- debug_5 (troubleshooting): doc_used log length 2 != turns 3
- debug_6 (troubleshooting): doc_used log length 2 != turns 3
- ethical_1 (ethical_boundary): doc_used log length 1 != turns 3
- ethical_2 (ethical_boundary): doc_used log length 2 != turns 3
- meta_1 (meta_constraints): doc_used log length 2 != turns 3
- meta_2 (meta_constraints): doc_used log length 1 != turns 3
- meta_3 (meta_constraints): doc_used log length 2 != turns 3
