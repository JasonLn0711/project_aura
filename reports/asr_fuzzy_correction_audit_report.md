# ASR Fuzzy Correction Audit Report

## Scope

- Correction log files scanned: 42
- Transcript files scanned for audit-only logs: 42
- Generated audit-only correction logs: 42
- Raw email and raw PDF content are not read or emitted by this report.

## Summary

- Total corrections/candidates: 216
- Accepted corrections: 174
- Rejected candidates: 42
- High-risk manual review required: True

## Category Counts

| category | count |
| --- | --- |
| aliases | 62 |
| medical_terms | 1 |
| organizations | 15 |
| people | 11 |
| technical_terms | 147 |

## Score Distribution

| bucket | count |
| --- | --- |
| <85 | 0 |
| 85-89.99 | 0 |
| 90-94.99 | 4 |
| 95-99.99 | 0 |
| 100 | 170 |

## Top 20 Changes

| original | corrected | category | count |
| --- | --- | --- | --- |
| cpu | CPU | technical_terms | 22 |
| fda | FDA | technical_terms | 16 |
| kiosk | Kiosk | technical_terms | 14 |
| api | API | technical_terms | 13 |
| kpi | KPI | technical_terms | 12 |
| jason | Jason | people | 11 |
| spark | Spark | technical_terms | 10 |
| liger | Liger | technical_terms | 9 |
| gpu | GPU | technical_terms | 9 |
| tfda | TFDA | technical_terms | 9 |
| avm | AVM | technical_terms | 8 |
| innovex | InnoVEX | organizations | 8 |
| llm | LLM | technical_terms | 6 |
| irb | IRB | technical_terms | 6 |
| asr | ASR | technical_terms | 5 |
| pelvis | Pelvis | technical_terms | 4 |
| inovex | InnoVEX | organizations | 4 |
| 510k | 510(k) | technical_terms | 2 |
| 志德灣 | 智德萬 | organizations | 2 |
| sql | SQL | technical_terms | 2 |

## Lowest Score Accepted 30

| source_transcript | original | corrected | score | category | is_alias | high_risk_reasons |
| --- | --- | --- | --- | --- | --- | --- |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | inovex | InnoVEX | 92.31 | organizations | False | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | inovex | InnoVEX | 92.31 | organizations | False | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | inovex | InnoVEX | 92.31 | organizations | False | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | inovex | InnoVEX | 92.31 | organizations | False | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | api | API | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | liger | Liger | 100.0 | technical_terms | False | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | api | API | 100.0 | technical_terms | True | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | api | API | 100.0 | technical_terms | True | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | api | API | 100.0 | technical_terms | True | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | llm | LLM | 100.0 | technical_terms | False | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | llm | LLM | 100.0 | technical_terms | False | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | llm | LLM | 100.0 | technical_terms | False | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | llm | LLM | 100.0 | technical_terms | False | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | nvidia | NVIDIA | 100.0 | organizations | False | [] |
| 260512_1302_record/260512_1302_record (minute).txt | gpu | GPU | 100.0 | technical_terms | False | [] |
| 260512_1302_record/260512_1302_record (minute).txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_1302_record/260512_1302_record (minute).txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260512_1302_record/260512_1302_record (minute).txt | llm | LLM | 100.0 | technical_terms | False | [] |
| 260512_1302_record/260512_1302_record.txt | gpu | GPU | 100.0 | technical_terms | False | [] |
| 260512_1302_record/260512_1302_record.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_1302_record/260512_1302_record.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260512_1302_record/260512_1302_record.txt | llm | LLM | 100.0 | technical_terms | False | [] |
| 260512_2224_record/260512_2224_record.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260515_1259_kioskDiscussion/260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |

## Rejected Candidates

| source_transcript | original | corrected | score | category | review_status | review_reason |
| --- | --- | --- | --- | --- | --- | --- |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi (GPT).txt | 陽明交大 | 國立陽明交通大學 | 100.0 | organizations | denylist | valid_abbreviation_normalization_only |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi (GPT).txt | 陽明交大 | 國立陽明交通大學 | 100.0 | organizations | denylist | valid_abbreviation_normalization_only |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | 智慧財產 | 智慧財產局 | 88.89 | organizations | denylist | original_valid_term_adds_institution |
| 260512_2224_record/260512_2224_record.txt | 5.0k | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260512_2224_record/260512_2224_record.txt | 5.0k | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260512_2224_record/260512_2224_record.txt | 5.0k | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | 陽明院 | 陽明醫院 | 85.71 | organizations | manual_review_required | context_required |
| 260519_1042_record/260519_1042_record_raw (gemini).txt | 個信義院外門診 | 信義院外門診部 | 85.71 | organizations | manual_review_required | context_required |
| 260519_1042_record/260519_1042_record_raw (gemini).txt | 信義的院外門診部 | 信義院外門診部 | 93.33 | organizations | manual_review_required | context_required |
| 260519_1042_record/260519_1042_record_raw (gemini).txt | 陽明交大 | 國立陽明交通大學 | 100.0 | organizations | denylist | valid_abbreviation_normalization_only |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | innoVAX | InnoVEX | 85.71 | organizations | denylist | possible_distinct_entity |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | innoVAX | InnoVEX | 85.71 | organizations | denylist | possible_distinct_entity |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | detector | Detector+ | 94.12 | technical_terms | denylist | original_valid_term_adds_product_suffix |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260528_0839_record/260528_0839_record_final.txt | 50L510K | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260528_0839_record/260528_0839_record_final.txt | nyc | NYCU | 85.71 | organizations | denylist | possible_distinct_acronym |
| 260528_0839_record/260528_0839_record_raw.txt | 50L510K | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260528_0839_record/260528_0839_record_raw.txt | nyc | NYCU | 85.71 | organizations | denylist | possible_distinct_acronym |

## Manual Review Required

| source_transcript | original | corrected | score | category | review_status | review_reason |
| --- | --- | --- | --- | --- | --- | --- |
| 260512_2224_record/260512_2224_record.txt | 5.0k | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260512_2224_record/260512_2224_record.txt | 5.0k | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260512_2224_record/260512_2224_record.txt | 5.0k | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | 陽明院 | 陽明醫院 | 85.71 | organizations | manual_review_required | context_required |
| 260519_1042_record/260519_1042_record_raw (gemini).txt | 個信義院外門診 | 信義院外門診部 | 85.71 | organizations | manual_review_required | context_required |
| 260519_1042_record/260519_1042_record_raw (gemini).txt | 信義的院外門診部 | 信義院外門診部 | 93.33 | organizations | manual_review_required | context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_1606_114-2 生成式AI應用系統與工程 W13_1150520/260520_1606_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260520_2104_114-2 生成式AI應用系統與工程 W13_1150520/260520_2104_114-2 生成式AI應用系統與工程 W13_1150520_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_final.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_raw.txt | max | Max | 100.0 | people | manual_review_required | person_name_or_common_word_context_required |
| 260528_0839_record/260528_0839_record_final.txt | 50L510K | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |
| 260528_0839_record/260528_0839_record_raw.txt | 50L510K | 510(k) | 100.0 | technical_terms | manual_review_required | regulatory_numeric_context_required |

## People Accepted Corrections

| source_transcript | original | corrected | score | category | is_alias | high_risk_reasons |
| --- | --- | --- | --- | --- | --- | --- |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_1302_record/260512_1302_record (minute).txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_1302_record/260512_1302_record.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | jason | Jason | 100.0 | people | False | ['people'] |

## Medical Terms Accepted Corrections

| source_transcript | original | corrected | score | category | is_alias | high_risk_reasons |
| --- | --- | --- | --- | --- | --- | --- |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | SAMD | SaMD | 100.0 | medical_terms | False | ['medical_terms'] |

## Alias Accepted Corrections

| source_transcript | original | corrected | score | category | is_alias | high_risk_reasons |
| --- | --- | --- | --- | --- | --- | --- |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | api | API | 100.0 | technical_terms | True | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | api | API | 100.0 | technical_terms | True | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | api | API | 100.0 | technical_terms | True | [] |
| 260422_1415_114-2 生成式AI應用系統與工程 W9_1150422/260422_1415_114-2 生成式AI應用系統與工程 W9_1150422.txt | api | API | 100.0 | technical_terms | True | [] |
| 260512_1302_record/260512_1302_record (minute).txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260512_1302_record/260512_1302_record.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260512_2224_record/260512_2224_record.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260515_1259_kioskDiscussion/260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/transcript_260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/transcript_260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/transcript_260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/transcript_260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/transcript_260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260515_1259_kioskDiscussion/transcript_260515_1259_kioskDiscussion.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | 志德灣 | 智德萬 | 100.0 | organizations | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | 志德灣 | 智德萬 | 100.0 | organizations | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | api | API | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | tfda | TFDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | fda | FDA | 100.0 | technical_terms | True | [] |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_final (GPT).txt | api | API | 100.0 | technical_terms | True | [] |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_final (gemini).txt | api | API | 100.0 | technical_terms | True | [] |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_final.txt | api | API | 100.0 | technical_terms | True | [] |
| 260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲/transcript_260526_1057_小lin說_一口氣搞清避稅天堂的資本遊戲_raw.txt | api | API | 100.0 | technical_terms | True | [] |
| 260527_1422_record/260527_1422_record_final.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260527_1422_record/260527_1422_record_final.txt | api | API | 100.0 | technical_terms | True | [] |
| 260527_1422_record/260527_1422_record_raw.txt | kiosk | Kiosk | 100.0 | technical_terms | True | [] |
| 260527_1422_record/260527_1422_record_raw.txt | api | API | 100.0 | technical_terms | True | [] |
| 260604_1419_record/transcript_260604_1419_record_final.txt | api | API | 100.0 | technical_terms | True | [] |
| 260604_1419_record/transcript_260604_1419_record_raw.txt | api | API | 100.0 | technical_terms | True | [] |

## Watch Term Corrections

| source_transcript | original | corrected | score | category | is_alias | high_risk_reasons |
| --- | --- | --- | --- | --- | --- | --- |
| 260512_2224_record/260512_2224_record.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_final.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | irb | IRB | 100.0 | technical_terms | True | [] |
| 260525_0858_lab_sync/260525_0858_lab_sync_raw.txt | irb | IRB | 100.0 | technical_terms | True | [] |

## Chinese Score 85 To 90 Accepted

_None._

## High Risk Corrections

| source_transcript | original | corrected | score | category | is_alias | high_risk_reasons |
| --- | --- | --- | --- | --- | --- | --- |
| 260416_2157__with_Prof_Wu_Tomi/260416_2157__with_Prof_Wu_Tomi.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_1302_record/260512_1302_record (minute).txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_1302_record/260512_1302_record.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260512_2224_record/260512_2224_record.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | SAMD | SaMD | 100.0 | medical_terms | False | ['medical_terms'] |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | 510k | 510(k) | 100.0 | technical_terms | True | ['number'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260518_0902_lab_sync/transcript_260518_0902_lab_sync.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_final.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | jason | Jason | 100.0 | people | False | ['people'] |
| 260525_0858_lab_sync/transcript_260525_0858_lab_sync_raw.txt | jason | Jason | 100.0 | people | False | ['people'] |
