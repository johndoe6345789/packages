
---
Split out of `metabuilder/packages` as part of the [reposplit](https://github.com/johndoe6345789/reposplit) effort. Packages that already had a specific home (codegen_studio, code_editor, email_client, dbal-related, media_center, geocities-app, testing-related, workflow_editor) were excluded here since they were already migrated elsewhere.

Note: several of these (admin, ui_auth, ui_login, ui_permissions, role_editor, user_manager, audit_log, dashboard, nav_menu, ui_header/footer/home/intro/pages, notification_center, config_summary) are consumed by `metabuilder/frontends/nextjs`, which stays in the fat repo. Moving them here may need reconciling with that dependency later.
