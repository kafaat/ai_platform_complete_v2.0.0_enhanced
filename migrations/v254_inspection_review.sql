BEGIN;
ALTER TABLE inspection_handoffs
    DROP CONSTRAINT IF EXISTS inspection_handoffs_action_check,
    DROP CONSTRAINT IF EXISTS inspection_handoffs_check,
    DROP CONSTRAINT IF EXISTS inspection_handoff_event_ck;
ALTER TABLE inspection_handoffs ADD CONSTRAINT inspection_handoff_event_ck CHECK (
    (action='accept' AND actor=assignee AND previous_assignee=assignee AND reason IS NULL)
 OR (action='reopen' AND previous_assignee=assignee AND reason IS NULL)
 OR (action='reassign' AND previous_assignee<>assignee AND reason IS NOT NULL AND length(btrim(reason))>0)
 OR (action IN ('submit','approve','return') AND previous_assignee=assignee
     AND (actor=assignee)=(action='submit') AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 2000)
);
COMMIT;
