/**
 * @description Tests for AccountTriggerHandler and AccountTrigger.
 */
@IsTest
public with sharing class AccountTriggerTest {

    @IsTest
    static void testBeforeInsertUpdate_TrimsAndLowercases() {
        User u = [SELECT Id FROM User WHERE Id = :UserInfo.getUserId() LIMIT 1];
        System.runAs(u) {
            Account acc = new Account(
                Name = '  Acme Corp  ',
                Website = 'HTTP://EXAMPLE.COM'
            );

            Test.startTest();
            insert acc;
            Test.stopTest();

            if (!Schema.sObjectType.Account.isAccessible()) {
                System.assert(false, 'Account should be accessible for test queries.');
            }

            Account inserted = [
                SELECT Name, Website
                FROM Account
                WHERE Id = :acc.Id
                WITH USER_MODE
                LIMIT 1
            ];

            System.assertEquals('Acme Corp', inserted.Name, 'Name should be trimmed on insert.');
            System.assertEquals('http://example.com', inserted.Website, 'Website should be lowercased on insert.');
        }
    }

    @IsTest
    static void testBeforeInsertUpdate_TrimsPhoneOnUpdate() {
        User u = [SELECT Id FROM User WHERE Id = :UserInfo.getUserId() LIMIT 1];
        System.runAs(u) {
            Account acc = new Account(Name = 'Phone Test');
            insert acc;

            acc.Phone = '  555-0100  ';

            Test.startTest();
            update acc;
            Test.stopTest();

            if (!Schema.sObjectType.Account.isAccessible()) {
                System.assert(false, 'Account should be accessible for test queries.');
            }

            Account updated = [
                SELECT Phone
                FROM Account
                WHERE Id = :acc.Id
                WITH USER_MODE
                LIMIT 1
            ];

            System.assertEquals('555-0100', updated.Phone, 'Phone should be trimmed on update.');
        }
    }
}
