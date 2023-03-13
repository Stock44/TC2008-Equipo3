using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using Confluent.Kafka;
using UnityEngine;


namespace Kafka
{
    [Serializable]
    public class KafkaConsumer<TMessage>
    {
        private ConsumerConfig _consumerConfig;
        private Action<TMessage> _onMessageCallback;
        private string _topicName;

        public KafkaConsumer(string serverAddress, string topicName, Action<TMessage> onMessageCallback)
        {
            _onMessageCallback = onMessageCallback;

            _topicName = topicName;

            _consumerConfig = new ConsumerConfig
            {
                GroupId = "c#test-consumer-group" +
                          DateTime.Now, // unique group, so each listener gets all messages
                BootstrapServers = serverAddress,
                AutoOffsetReset = AutoOffsetReset.Latest
            };
        }


        public void StartKafkaListener(CancellationToken cancellationToken)
        {
            Debug.Log("Kafka - Starting thread");

            using (var consumer = new ConsumerBuilder<Ignore, string>(_consumerConfig).Build())
            {
                consumer.Subscribe(_topicName);

                while (!cancellationToken.IsCancellationRequested)
                {
                    try
                    {
                        // Waiting for message
                        var cr = consumer.Consume(cancellationToken);
                        // Got message! Decode and put on queue
                        TMessage message = JsonUtility.FromJson<TMessage>(cr.Message.Value);
                        _onMessageCallback(message);
                    }
                    catch (ConsumeException e)
                    {
                        Debug.Log("Kafka - Error occured: " + e.Error.Reason);
                    }
                    catch (OperationCanceledException e)
                    {
                        Debug.Log("Kafka - Consumer canceled");
                        break;
                    }
                }
            }
        }
    }
}