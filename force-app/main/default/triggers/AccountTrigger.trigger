trigger AccountTrigger on Account (before insert, before update) {
    if (Trigger.isBefore && (Trigger.isInsert || Trigger.isUpdate)) {
        AccountTriggerHandler.beforeInsertUpdate(Trigger.new, Trigger.oldMap);
    }
}
