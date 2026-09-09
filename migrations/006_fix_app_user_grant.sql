-- Session creation locks the account against concurrent deactivation.
-- PostgreSQL locking SELECT requires UPDATE privilege on the locked relation.
GRANT UPDATE ON core.app_user TO clinic_app;
