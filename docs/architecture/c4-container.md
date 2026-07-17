# Container Diagram

The deployable units that make up **ai-doc-organizer**, seeded from detected
structure. Each `Container(...)` entry follows the c4/v1 declared-container
shape (see ARCHITECTURE.md) so the maintenance pipeline can compare it against
the code. Refine labels, technologies, and relationships as needed.

```mermaid
C4Container
    title Container diagram for ai-doc-organizer

    Person(user, "User", "Uses ai-doc-organizer")

    Container_Boundary(ai-doc-organizer_boundary, "ai-doc-organizer") {
        Container(aido, "aido", "Python 3.14 — CLI + web UI")
    }

    Rel(user, aido, "Uses")
```
