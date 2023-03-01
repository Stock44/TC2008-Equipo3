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


        public void StartKafkaListener()
        {
            Debug.Log("Kafka - Starting Thread..");
            try
            {
                Debug.Log("Kafka - Created config");

                using var consumer = new ConsumerBuilder<Ignore, string>(_consumerConfig).Build();

                consumer.Subscribe(_topicName);
                Debug.Log("Kafka - Subscribed");

                CancellationTokenSource cts = new CancellationTokenSource();
                Console.CancelKeyPress += (_, e) =>
                {
                    e.Cancel = true; // prevent the process from terminating.
                    cts.Cancel();
                };

                try
                {
                    while (true)
                    {
                        try
                        {
                            // Waiting for message
                            var cr = consumer.Consume(cts.Token);
                            // Got message! Decode and put on queue
                            TMessage message = JsonUtility.FromJson<TMessage>(cr.Message.Value);
                            _onMessageCallback(message);
                        }
                        catch (ConsumeException e)
                        {
                            Debug.Log("Kafka - Error occured: " + e.Error.Reason);
                        }
                    }
                }
                catch (OperationCanceledException)
                {
                    Debug.Log("Kafka - Canceled..");
                    // Ensure the consumer leaves the group cleanly and final offsets are committed.
                    consumer.Close();
                }
            }
            catch (Exception ex)
            {
                Debug.Log("Kafka - Received Expection: " + ex.Message + " trace: " + ex.StackTrace);
            }
        }
    }
}