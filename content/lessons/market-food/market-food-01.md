---
id: en-prea1-market-food-01
class: demo-grade4
title: Market & Food — I would like…, please
level: pre-A1
duration_min: 45
delivery_mode: autonomous_class
lesson_schema_version: 1
fallback_language: vi
focus: [food_recognition, polite_request]
review: [greetings]
students_to_check: []
vocabulary: [apple, banana, rice, bread, water, egg]
target_phrases:
  - "I would like an apple, please."
curriculum:
  locale: en-VN
  learnerWedge: "Vietnam Grade 4 pre-A1 learners; progression aligned toward A1 can-do descriptors"
  frameworkRefs:
    - VN-GE-2018-EN-COMMUNICATIVE
    - CEFR-YL-PREA1-SPOKEN-REQUEST
  objectives:
    - id: food-recognise-6
      description: "Recognise six familiar food and drink words with picture support."
      evidence: "Anonymous board practice plus sampled selected-individual retrieval."
    - id: polite-request-frame
      description: "Use 'I would like ___, please' in a supported market exchange."
      evidence: "Pair participation plus sampled answer-station production."
  approver: "UNASSIGNED — curriculum review required before classroom release"
  approvalStatus: draft
session_plan:
  # The authored worst path enters CLOSURE by 43.7 minutes and finishes by
  # 44.7. EXIT is lesson time, not reserve time; reserve protects only the
  # final closing minute.
  durationMin: 45
  closureReserveS: 60
  namedTurnBudget: 8
  fairnessCooldown: 3
---

# Product lesson candidate — curriculum approval pending

This is the first complete autonomous-classroom lesson candidate. It is not the
format fixture and must not be labelled classroom-ready until a named English
teacher approves the language, pacing and assessment rubric. Prices and
`How much?` are deliberately outside this lesson.

## hook_market — HOOK

```yaml
scene: image
props: { asset: "asset://market/market.svg", caption: "At the market" }
duration_s: 90
say:
  - "Good morning, everyone. Today our classroom becomes a market. @happy"
  - "Look carefully. What food can you already see? Show me with your hands. @curious"
goto: baseline
teaching:
  stage: HOOK
  stageBudgetS: 90
  responseScope: anonymous
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: none
  recovery: { easierActivityId: input_one, safeDefaultActivityId: input_one }
  checkpoint: true
```

## baseline — BASELINE

```yaml
scene: vocabulary
props:
  items:
    - { id: apple, text: apple, asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
    - { id: water, text: water, asset: "asset://market/water.svg" }
  interaction: tap
duration_s: 90
say:
  - "No names yet. As a class, point to one word you know. @question"
expect: { kind: point, correct: apple, fuzzy: [banana, water] }
on:
  correct: { goto: input_one, say: ["I can see what the class remembers. @neutral"] }
  near: { goto: input_one, say: ["Thank you. Let us learn all six together. @neutral"] }
  wrong: { goto: input_one, say: ["Thank you. This is only our starting point. @neutral"] }
  uncertain: { goto: input_one, say: ["I am not sure what the class chose. Let us begin together. @neutral"] }
  unhandled: { goto: input_one, say: ["We will keep that thought and begin our market lesson. @neutral"] }
  silence: { goto: input_one, say: ["You may watch first. Let us begin together. @neutral"] }
  timeout: { goto: input_one, say: ["Let us begin together. @neutral"] }
teaching:
  stage: BASELINE
  stageBudgetS: 90
  responseScope: anonymous
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: class_aggregate
  recovery: { easierActivityId: input_one, safeDefaultActivityId: input_one }
```

## input_one — INPUT

```yaml
scene: vocabulary
props:
  items:
    - { id: apple, text: apple, asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
    - { id: rice, text: rice, asset: "asset://market/rice.svg" }
  interaction: none
duration_s: 150
say:
  - "Look and listen. Apple. Banana. Rice. @neutral"
  - "Touch your head for apple, shoulders for banana, and knees for rice. @happy"
goto: input_two
teaching:
  stage: INPUT
  stageBudgetS: 150
  responseScope: choral
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: participation
  recovery: { easierActivityId: input_one, safeDefaultActivityId: input_two }
```

## input_two — INPUT

```yaml
scene: vocabulary
props:
  items:
    - { id: bread, text: bread, asset: "asset://market/bread.svg" }
    - { id: water, text: water, asset: "asset://market/water.svg" }
    - { id: egg, text: egg, asset: "asset://market/egg.svg" }
  interaction: none
duration_s: 150
say:
  - "Now bread. Water. Egg. Listen once, then join me. @neutral"
  - "Bread. Water. Egg. Excellent effort, everyone. @happy"
goto: chorus
teaching:
  stage: INPUT
  stageBudgetS: 150
  responseScope: choral
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: participation
  recovery: { easierActivityId: input_two, safeDefaultActivityId: chorus }
```

## chorus — CHORUS_GESTURE

```yaml
scene: vocabulary
props:
  items:
    - { id: apple, text: apple, asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
    - { id: rice, text: rice, asset: "asset://market/rice.svg" }
    - { id: bread, text: bread, asset: "asset://market/bread.svg" }
    - { id: water, text: water, asset: "asset://market/water.svg" }
    - { id: egg, text: egg, asset: "asset://market/egg.svg" }
  interaction: none
duration_s: 240
say:
  - "When the picture lights up, say the word and show its gesture. @question"
  - "First slowly. Then we will try one quick round. @happy"
goto: guided_choice
teaching:
  stage: CHORUS_GESTURE
  stageBudgetS: 240
  responseScope: choral
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: participation
  recovery: { easierActivityId: input_one, safeDefaultActivityId: guided_choice }
  checkpoint: true
```

## guided_choice — GUIDED_PRACTICE

```yaml
scene: choice
props:
  prompt: "Which one do you drink?"
  options:
    - { id: water, text: water, asset: "asset://market/water.svg" }
    - { id: rice, text: rice, asset: "asset://market/rice.svg" }
    - { id: bread, text: bread, asset: "asset://market/bread.svg" }
duration_s: 180
say:
  - "Board team, which one do you drink? Choose together. @question"
expect: { kind: choice, correct: water }
on:
  correct: { goto: guided_point, say: ["Water is the drink. @happy"] }
  wrong: { goto: guided_help, say: ["Not yet. We eat that one. @curious"] }
  uncertain: { goto: guided_help, say: ["I am not sure which choice the class made. Let us make it easier. @neutral"] }
  unhandled: { goto: guided_help, say: ["We will return to that later. First, let us find the drink. @neutral"] }
  silence: { goto: guided_help, say: ["Let us remove one choice. @think"] }
  timeout: { goto: guided_help, say: ["Let us remove one choice. @think"] }
teaching:
  stage: GUIDED_PRACTICE
  stageBudgetS: 180
  responseScope: anonymous
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: class_aggregate
  recovery: { easierActivityId: guided_help, safeDefaultActivityId: guided_help }
```

## guided_help — RECOVERY

```yaml
scene: vocabulary
props:
  items:
    - { id: water, text: water, asset: "asset://market/water.svg" }
    - { id: bread, text: bread, asset: "asset://market/bread.svg" }
  interaction: none
  highlightId: water
duration_s: 60
say:
  - "We drink water. Say water once with me. @neutral"
goto: guided_point
teaching:
  stage: GUIDED_PRACTICE
  stageBudgetS: 60
  responseScope: choral
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: participation
  recovery: { easierActivityId: guided_help, safeDefaultActivityId: guided_point }
```

## guided_point — GUIDED_PRACTICE

```yaml
scene: vocabulary
props:
  items:
    - { id: apple, text: apple, asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
    - { id: egg, text: egg, asset: "asset://market/egg.svg" }
  interaction: point
duration_s: 180
say:
  - "Point to the egg. Work as one board team. @question"
expect: { kind: point, correct: egg }
on:
  correct: { goto: request_frame, say: ["That is the egg. @happy"] }
  wrong: { goto: request_frame, say: ["The egg is this one. Look, then we move on. @neutral"] }
  uncertain: { goto: request_frame, say: ["I am not sure which picture was selected. Here is the egg. @neutral"] }
  unhandled: { goto: request_frame, say: ["We will park that question and continue with our market request. @neutral"] }
  silence: { goto: request_frame, say: ["Here is the egg. @neutral"] }
  timeout: { goto: request_frame, say: ["Here is the egg. @neutral"] }
teaching:
  stage: GUIDED_PRACTICE
  stageBudgetS: 180
  responseScope: anonymous
  participationMode: whole_class
  skillIds: [food_recognition]
  evidencePolicy: class_aggregate
  recovery: { easierActivityId: guided_help, safeDefaultActivityId: request_frame }
  checkpoint: true
```

## request_frame — LANGUAGE_FRAME

```yaml
scene: sentence_builder
props:
  tokens:
    - { id: i, text: I }
    - { id: would, text: would }
    - { id: like, text: like }
    - { id: an_apple, text: an apple }
    - { id: please, text: please. }
  placed: [i, would, like, an_apple, please]
  target: "I would like an apple, please."
duration_s: 180
say:
  - "At the market, listen to this polite request. I would like an apple, please. @neutral"
  - "Say it with me in three parts: I would like — an apple — please. @happy"
goto: pair_demo
teaching:
  stage: LANGUAGE_FRAME
  stageBudgetS: 180
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: pair_demo }
```

## pair_demo — PAIR_SETUP

```yaml
scene: roleplay
props:
  environment: market stall
  aiRole: shopkeeper
  studentRole: customer
  targetPhrases: ["I would like an apple, please."]
duration_s: 120
say:
  - "Partner A is the customer. Partner B is the shopkeeper. Watch one example. @question"
  - "Customer: I would like an apple, please. Shopkeeper: Here you are. @neutral"
goto: pair_roleplay
teaching:
  stage: PAIR_SETUP
  stageBudgetS: 120
  responseScope: group
  participationMode: pair
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: pair_demo, safeDefaultActivityId: pair_roleplay }
```

## pair_roleplay — PAIR_PRODUCTION

```yaml
scene: roleplay
props:
  environment: market stall
  aiRole: timekeeper
  studentRole: customer and shopkeeper
  targetPhrases: ["I would like ___, please.", "Here you are."]
duration_s: 300
say:
  - "Pairs, begin. Choose any one food. After two minutes, swap roles. @happy"
  - "If you forget, point to the sentence frame on the board. @neutral"
goto: answer_station_invite
teaching:
  stage: PAIR_PRODUCTION
  stageBudgetS: 300
  responseScope: group
  participationMode: pair
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: pair_demo, safeDefaultActivityId: answer_station_invite }
  checkpoint: true
```

## answer_station_invite — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props:
  environment: answer station market
  aiRole: shopkeeper
  studentRole: selected customer
  targetPhrases: ["I would like ___, please."]
duration_s: 60
say:
  - "Now selected customers will visit the answer station. Wait for your name, walk to the microphone, then press Ready. @neutral"
goto: answer_station_01_apple
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 60
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_01_apple }
```

## answer_station_01_apple — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props:
  environment: answer station market
  aiRole: shopkeeper
  studentRole: selected customer
  targetPhrases: ["I would like an apple, please."]
duration_s: 30
say:
  - "Customer one, welcome to the market. Ask for an apple. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like an apple please"]
  fuzzy: ["i like an apple please", "i would like apple please"]
on:
  correct: { goto: answer_station_02_banana, say: ["Thank you. Here is your apple. @happy"] }
  near: { goto: answer_station_help_01_apple, say: ["I heard your request. Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_01_apple, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_01_apple, say: ["I could not hear one clear voice. We will use the sentence frame. @neutral"] }
  unhandled: { goto: answer_station_help_01_apple, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_01_apple, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_01_apple, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_01_apple, safeDefaultActivityId: answer_station_02_banana }
```

## answer_station_help_01_apple — RECOVERY

```yaml
scene: sentence_builder
props:
  tokens: [{ id: i_would_like, text: I would like }, { id: food, text: an apple }, { id: please, text: please. }]
  placed: [i_would_like, food, please]
  target: "I would like an apple, please."
duration_s: 20
say:
  - "Everyone, read the three chunks together: I would like — an apple — please. @neutral"
goto: answer_station_02_banana
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_02_banana }
```

## answer_station_02_banana — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like a banana, please."] }
duration_s: 30
say:
  - "Next customer, ask for a banana. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like a banana please"]
  fuzzy: ["i like a banana please", "i would like banana please"]
on:
  correct: { goto: answer_station_03_bread, say: ["Thank you. Here is your banana. @happy"] }
  near: { goto: answer_station_help_02_banana, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_02_banana, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_02_banana, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_02_banana, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_02_banana, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_02_banana, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_02_banana, safeDefaultActivityId: answer_station_03_bread }
```

## answer_station_help_02_banana — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: a banana }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like a banana, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — a banana — please. @neutral"
goto: answer_station_03_bread
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_03_bread }
```

## answer_station_03_bread — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like bread, please."] }
duration_s: 30
say:
  - "Next customer, ask for bread. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like bread please"]
  fuzzy: ["i like bread please", "i would like the bread please"]
on:
  correct: { goto: answer_station_04_egg, say: ["Thank you. Here is your bread. @happy"] }
  near: { goto: answer_station_help_03_bread, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_03_bread, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_03_bread, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_03_bread, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_03_bread, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_03_bread, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_03_bread, safeDefaultActivityId: answer_station_04_egg }
```

## answer_station_help_03_bread — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: bread }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like bread, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — bread — please. @neutral"
goto: answer_station_04_egg
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_04_egg }
```

## answer_station_04_egg — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like an egg, please."] }
duration_s: 30
say:
  - "Next customer, ask for an egg. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like an egg please"]
  fuzzy: ["i like an egg please", "i would like egg please"]
on:
  correct: { goto: answer_station_05_rice, say: ["Thank you. Here is your egg. @happy"] }
  near: { goto: answer_station_help_04_egg, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_04_egg, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_04_egg, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_04_egg, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_04_egg, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_04_egg, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_04_egg, safeDefaultActivityId: answer_station_05_rice }
```

## answer_station_help_04_egg — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: an egg }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like an egg, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — an egg — please. @neutral"
goto: answer_station_05_rice
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_05_rice }
```

## answer_station_05_rice — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like rice, please."] }
duration_s: 30
say:
  - "Next customer, ask for rice. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like rice please"]
  fuzzy: ["i like rice please", "i would like the rice please"]
on:
  correct: { goto: answer_station_06_water, say: ["Thank you. Here is your rice. @happy"] }
  near: { goto: answer_station_help_05_rice, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_05_rice, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_05_rice, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_05_rice, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_05_rice, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_05_rice, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_05_rice, safeDefaultActivityId: answer_station_06_water }
```

## answer_station_help_05_rice — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: rice }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like rice, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — rice — please. @neutral"
goto: answer_station_06_water
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_06_water }
```

## answer_station_06_water — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like water, please."] }
duration_s: 30
say:
  - "Next customer, ask for water. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like water please"]
  fuzzy: ["i like water please", "i would like the water please"]
on:
  correct: { goto: answer_station_07_apple, say: ["Thank you. Here is your water. @happy"] }
  near: { goto: answer_station_help_06_water, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_06_water, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_06_water, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_06_water, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_06_water, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_06_water, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_06_water, safeDefaultActivityId: answer_station_07_apple }
```

## answer_station_help_06_water — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: water }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like water, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — water — please. @neutral"
goto: answer_station_07_apple
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_07_apple }
```

## answer_station_07_apple — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like an apple, please."] }
duration_s: 30
say:
  - "Next customer, ask for an apple again. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like an apple please"]
  fuzzy: ["i like an apple please", "i would like apple please"]
on:
  correct: { goto: answer_station_08_bread, say: ["Thank you. Here is your apple. @happy"] }
  near: { goto: answer_station_help_07_apple, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_07_apple, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_07_apple, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_07_apple, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_07_apple, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_07_apple, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_07_apple, safeDefaultActivityId: answer_station_08_bread }
```

## answer_station_help_07_apple — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: an apple }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like an apple, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — an apple — please. @neutral"
goto: answer_station_08_bread
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: answer_station_08_bread }
```

## answer_station_08_bread — SAMPLED_RETRIEVAL

```yaml
scene: roleplay
props: { environment: answer station market, aiRole: shopkeeper, studentRole: selected customer, targetPhrases: ["I would like bread, please."] }
duration_s: 30
say:
  - "Last customer, ask for bread. Press Ready, then speak. @question"
expect:
  kind: speech
  correct: ["i would like bread please"]
  fuzzy: ["i like bread please", "i would like the bread please"]
on:
  correct: { goto: explore_transfer, say: ["Thank you. Here is your bread. @happy"] }
  near: { goto: answer_station_help_08_bread, say: ["Let us add the missing words together. @curious"] }
  wrong: { goto: answer_station_help_08_bread, say: ["Let us build the request together. @neutral"] }
  uncertain: { goto: answer_station_help_08_bread, say: ["We will use the sentence frame together. @neutral"] }
  unhandled: { goto: answer_station_help_08_bread, say: ["For this turn, let us practise our market request. @neutral"] }
  silence: { goto: answer_station_help_08_bread, say: ["No problem. Look at the sentence frame. @neutral"] }
  timeout: { goto: answer_station_help_08_bread, say: ["We will use the sentence frame together. @neutral"] }
teaching:
  stage: SAMPLED_RETRIEVAL
  stageBudgetS: 30
  responseScope: selected_individual
  participationMode: selected_individual
  skillIds: [polite_request]
  evidencePolicy: individual
  recovery: { easierActivityId: answer_station_help_08_bread, safeDefaultActivityId: explore_transfer }
```

## answer_station_help_08_bread — RECOVERY

```yaml
scene: sentence_builder
props: { tokens: [{ id: i_would_like, text: I would like }, { id: food, text: bread }, { id: please, text: please. }], placed: [i_would_like, food, please], target: "I would like bread, please." }
duration_s: 20
say:
  - "Everyone, read together: I would like — bread — please. @neutral"
goto: explore_transfer
teaching:
  stage: RECOVERY
  stageBudgetS: 20
  responseScope: choral
  participationMode: whole_class
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: explore_transfer }
```

## explore_transfer — EXPLORE_TRANSFER

```yaml
scene: explore
props:
  topic: "Foods in our local market"
  nodes:
    - { id: rice, label: rice, asset: "asset://market/rice.svg" }
    - { id: banana, label: banana, asset: "asset://market/banana.svg" }
    - { id: egg, label: egg, asset: "asset://market/egg.svg" }
duration_s: 180
say:
  - "Think of one food from a market near your home. Tell a partner: I would like blank, please. @curious"
  - "We stay with food requests today. Prices will be our next market lesson. @neutral"
goto: exit_check
teaching:
  stage: EXPLORE_TRANSFER
  stageBudgetS: 180
  responseScope: group
  participationMode: pair
  skillIds: [polite_request]
  evidencePolicy: participation
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: exit_check }
```

## exit_check — EXIT

```yaml
scene: choice
props:
  prompt: "Complete: I would like ___, please."
  options:
    - { id: bread, text: bread, asset: "asset://market/bread.svg" }
    - { id: hello, text: hello }
    - { id: blue, text: blue }
duration_s: 240
say:
  - "Final class check. Choose the food that completes our request. @question"
expect: { kind: choice, correct: bread }
on:
  correct: { goto: closure, say: ["Bread completes the request. @happy"] }
  wrong: { goto: closure, say: ["Bread is our food word. We will review it next time. @neutral"] }
  uncertain: { goto: closure, say: ["I am not sure which choice the class made. We will review the frame next time. @neutral"] }
  unhandled: { goto: closure, say: ["We will save that question for another lesson and close with our request. @neutral"] }
  silence: { goto: closure, say: ["We will begin next time with this sentence again. @neutral"] }
  timeout: { goto: closure, say: ["We will begin next time with this sentence again. @neutral"] }
teaching:
  stage: EXIT
  stageBudgetS: 240
  responseScope: anonymous
  participationMode: whole_class
  skillIds: [food_recognition, polite_request]
  evidencePolicy: class_aggregate
  recovery: { easierActivityId: request_frame, safeDefaultActivityId: closure }
  checkpoint: true
```

## closure — CLOSURE

```yaml
scene: text
props:
  text: "I would like ___, please."
  size: xl
duration_s: 60
say:
  - "Today you recognised six market words and practised one polite request. @happy"
  - "Thank your partner. The lesson is complete. @neutral"
teaching:
  stage: CLOSURE
  stageBudgetS: 60
  responseScope: anonymous
  participationMode: whole_class
  skillIds: [food_recognition, polite_request]
  evidencePolicy: none
  recovery: { easierActivityId: closure, safeDefaultActivityId: closure }
  checkpoint: true
```
