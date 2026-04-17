/**
 * @description Handler for Account trigger logic.
 */
public with sharing class AccountTriggerHandler {

    /**
     * @description Normalizes Account fields prior to insert and update.
     * @param newList The incoming Account records.
     * @param oldMap The previous Account records (null on insert).
     */
    public static void beforeInsertUpdate(List<Account> newList, Map<Id, Account> oldMap) {
        if (newList == null || newList.isEmpty()) {
            return;
        }

        Boolean canEditName = Trigger.isInsert
            ? Schema.sObjectType.Account.fields.Name.isCreateable()
            : Schema.sObjectType.Account.fields.Name.isUpdateable();
        Boolean canEditPhone = Trigger.isInsert
            ? Schema.sObjectType.Account.fields.Phone.isCreateable()
            : Schema.sObjectType.Account.fields.Phone.isUpdateable();
        Boolean canEditWebsite = Trigger.isInsert
            ? Schema.sObjectType.Account.fields.Website.isCreateable()
            : Schema.sObjectType.Account.fields.Website.isUpdateable();

        for (Account acc : newList) {
            if (canEditName && acc.Name != null) {
                acc.Name = acc.Name.trim();
            }
            if (canEditPhone && acc.Phone != null) {
                acc.Phone = acc.Phone.trim();
            }
            if (canEditWebsite && acc.Website != null) {
                acc.Website = acc.Website.trim().toLowerCase();
            }
        }
    }
}
