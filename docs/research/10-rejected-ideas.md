# Rejected Ideas

This document follows ASD-STE100 Simplified Technical English.

> "Every architecture is defined as much by what it rejects as by what it adopts."

## Purpose

This document records architectural directions that were deliberately postponed, avoided, or rejected.

Understanding these decisions helps prevent repeating previously evaluated ideas without new justification.

---

### Dashboard Before 1.0

Rejected as a release requirement. A web dashboard improves usability but does not determine architectural stability.

Priority should instead be given to:

- logging
- testing
- documentation
- setup reliability
- bug fixing

Dashboard functionality belongs in future releases after a stable foundation exists. :contentReference[oaicite:2]{index=2}

---

### Endless Feature Expansion

Rejected.

## Reasoning

Constantly adding new capabilities delays stable releases indefinitely.

Instead:

- freeze features
- release
- collect feedback
- iterate

Stable software is more valuable than perpetual development ([06-bee0d54-retrospective.md](./06-bee0d54-retrospective.md)). :contentReference[oaicite:3]{index=3}

---

### Provider-specific Architecture

Rejected. Allowing one provider to dictate architecture increases coupling and reduces flexibility.

Providers should remain interchangeable behind shared abstractions.

---

### Architecture by Convenience

Rejected. Convenient shortcuts often become long-term maintenance burdens.

Architectural changes should be intentional and discussed before implementation. :contentReference[oaicite:4]{index=4}

---

### Documentation as an Afterthought

Rejected. Documentation is part of the architecture.

Repository documentation remains the canonical specification, with the documentation website serving as a presentation layer. :contentReference[oaicite:5]{index=5}

---

### Releasing Too Late

Rejected.

Waiting for every planned feature postpones valuable feedback and increases maintenance pressure.

A stable release should mark architectural maturity rather than the absence of future ideas. :contentReference[oaicite:6]{index=6}

---

### Living Document

This document is expected to grow.

Whenever a major architectural proposal is consciously declined, record:

- the proposal
- the decision
- the reasoning
- any conditions under which it might be reconsidered

Future contributors should understand not only *what* the architecture is, but also *why alternative approaches were not chosen*.

---

### Related Research

- Architecture Philosophy ([01-architecture-philosophy.md](./01-architecture-philosophy.md))
- bee0d54 Retrospective ([06-bee0d54-retrospective.md](./06-bee0d54-retrospective.md))
- Dogma vs Doctrine ([08-dogma-vs-doctrine.md](./08-dogma-vs-doctrine.md))
- Decalogue ([09-decalogue.md](./09-decalogue.md))
- Provider Independence ([03-provider-independence.md](./03-provider-independence.md))
