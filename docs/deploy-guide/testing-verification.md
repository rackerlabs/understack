# Testing and Verification

After deploying a new Understack, we have a few tools available to help us test our new deployment
and ensure everything is working.

## OpenStack Tempest

We'll use [OpenStack Tempest](https://docs.openstack.org/tempest/latest/index.html)
to quickly perform API tests against Understack.

Here's a small example using tempest to run keypair tests against an Understack instance:

``` text
$ tempest run --concurrency 1 --serial --include-list include-keypair.txt
{0} tempest.api.compute.keypairs.test_keypairs.KeyPairsV2TestJSON.test_get_keypair_detail [1.563604s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs.KeyPairsV2TestJSON.test_keypair_create_delete [0.884011s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs.KeyPairsV2TestJSON.test_keypair_create_with_pub_key [0.893123s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs.KeyPairsV2TestJSON.test_keypairs_create_list_delete [3.178549s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_create_keypair_invalid_name [0.589208s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_create_keypair_when_public_key_bits_exceeds_maximum [0.432699s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_create_keypair_with_duplicate_name [1.471715s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_create_keypair_with_empty_name_string [0.540209s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_create_keypair_with_empty_public_key [0.440568s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_create_keypair_with_long_keynames [0.435756s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_keypair_create_with_invalid_pub_key [0.479691s] ... ok
{0} tempest.api.compute.keypairs.test_keypairs_negative.KeyPairsNegativeTestJSON.test_keypair_delete_nonexistent_key [0.509478s] ... ok

======
Totals
======
Ran: 12 tests in 12.3828 sec.
 - Passed: 12
 - Skipped: 0
 - Expected Fail: 0
 - Unexpected Success: 0
 - Failed: 0
Sum of execute time for each test: 11.4186 sec.

==============
Worker Balance
==============
 - Worker 0 (12 tests) => 0:00:12.382768
```

## OpenStack Rally

We'll also use [OpenStack Rally](https://docs.openstack.org/rally/latest/) to run integration and scenario tests.

See the [understack-tests](https://github.com/rackerlabs/understack/tree/main/python/understack-tests) in the understack repo
for docs on running our rally scenarios.
