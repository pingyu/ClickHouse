import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers.cluster import ClickHouseCluster
from helpers.network import PartitionManager

cluster = ClickHouseCluster(__file__)

# Cluster with 1 shard of 2 replicas. node is the instance with Distributed table.
node = cluster.add_instance(
    'node', with_zookeeper=True, main_configs=['configs/remote_servers.xml'], user_configs=['configs/users.xml'])
node_1 = cluster.add_instance('node_1', with_zookeeper=True, stay_alive=True, user_configs=['configs/users1.xml'])
node_2 = cluster.add_instance('node_2', with_zookeeper=True)

config = '''<yandex>
    <profiles>
        <default>
            <{setting}>30</{setting}>
        </default>
    </profiles>
</yandex>'''


@pytest.fixture(scope="module")
def started_cluster():
    try:
        cluster.start()

        node_1.query('''CREATE TABLE replicated (id UInt32, date Date) ENGINE =
            ReplicatedMergeTree('/clickhouse/tables/replicated', 'node_1')  ORDER BY id PARTITION BY toYYYYMM(date)''')

        node_2.query('''CREATE TABLE replicated (id UInt32, date Date) ENGINE =
            ReplicatedMergeTree('/clickhouse/tables/replicated', 'node_2')  ORDER BY id PARTITION BY toYYYYMM(date)''')
       
        node.query('''CREATE TABLE distributed (id UInt32, date Date) ENGINE =
            Distributed('test_cluster', 'default', 'replicated')''')

        yield cluster

    finally:
        cluster.shutdown()

def process_test(sleep_setting_name, receive_timeout_name):
    node_1.replace_config('/etc/clickhouse-server/users.d/users1.xml', config.format(setting=sleep_setting_name))

    # Restart node to make new config relevant
    node_1.restart_clickhouse(30)
    
    # Without hedged requests select query will last more than 30 seconds,
    # with hedged requests it will last just around 1-2 second

    start = time.time()
    node.query("SELECT * FROM distributed");
    query_time = time.time() - start
    
    print(query_time)


def test(started_cluster):
    node.query("INSERT INTO distributed VALUES (1, '2020-01-01')")

    process_test("sleep_before_send_hello", "receive_hello_timeout")
    process_test("sleep_before_send_tables_status", "receive_tables_status_timeout")
    process_test("sleep_before_send_data", "receive_data_timeout")

