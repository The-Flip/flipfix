This folder contains the developer guide.

AI assistants must follow these guides before responding:

1. [`HTML_CSS_Guide.md`](HTML_CSS_Guide.md) – enforce tokens, responsive rules, component patterns, etc.
2. [`Django_Python_Guide.md`](Django_Python_Guide.md) – Django/Python conventions, code organization, testing expectations, etc.
3. [`Testing_Guide.md`](Testing_Guide.md) – standardized test runner, layout, coverage expectations, etc.
4. [`Project_Structure.md`](Project_Structure.md) – keep contributions aligned with the target app layout.
5. [`Data_Model.md`](Data_Model.md) – respect the domain objects, fields, privacy constraints, etc.

AI assistants must confirm relevant sections from these documents before generating code or explanations.  Cite which guide sections informed the answer whenever practical.

## When rebuilding from scratch

When regenerating the project from scratch, look at this scaffolding information.

- [`scaffolding/HTML_CSS_Scaffold.md`](scaffolding/HTML_CSS_Scaffold.md) – tokens, layout baselines, and component defaults for regenerating the core stylesheet. 
- [`scaffolding/Django_Python_Scaffold.md`](scaffolding/Django_Python_Scaffold.md) – project layout, settings modules, data-seeding commands, and Render deployment hooks.
- [`scaffolding/Testing_Scaffold.md`](scaffolding/Testing_Scaffold.md) – baseline test directory structure, settings, and CI expectations.
