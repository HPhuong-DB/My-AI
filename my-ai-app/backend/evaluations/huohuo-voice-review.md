# Huohuo voice review — 2026-09-11

Changes: concise, shy but opinionated persona; situational humour; gentle responses during fatigue/distress; no obligatory questions or stuttering. Fast greetings share the same voice and honour stored pronouns. Added 18 evaluation turns across voice, boundaries, grounding and greetings; added deterministic tests for greeting variation, identity and pronoun parsing.

Automated verification: 201 backend tests passed. These verify routing, templates, persistence extraction and existing regressions, not the full semantic quality of generative replies. No frontend code changed in this task.

Real API evaluation: eval-74380b1df3e2.json contains six completed turns and successful disposable-user cleanup. Greeting took 87.9 ms total; model turns took about 5.3–24.8 seconds. Ghost humour, fatigue response and arithmetic correction matched the intended tone, but reproduced the corresponding prompt examples almost verbatim. This is evidence of style-following on demonstrated situations, not broad generalisation. The one-sentence Python explanation followed length but used an imprecise memory-location metaphor.

The run exposed an unrecognised reverse-order pronoun request (“Từ giờ xưng tớ và gọi mình là cậu nhé”), causing the quick greeting to fall back to mình–bạn. Fixed extraction with an anchored direct-request rule and tests excluding third-party/quoted/conditional speech. The remaining twelve scenario turns are provided for future evaluation and have not been run here.

Targeted final rerun: eval-aac987c8e389.json completed both pronoun-setting and greeting turns; greeting now uses tớ–cậu, took 119.5 ms total, and cleanup completed.
