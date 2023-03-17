using System;
using System.Collections;
using System.Threading;
using UnityEngine;
using System.Collections.Concurrent;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Confluent.Kafka;
using Unity.VisualScripting;

namespace Kafka
{
    public abstract class KafkaConsumerBehaviour<TMessage> : MonoBehaviour
    {
        Thread _kafkaThread;
        KafkaConsumer<TMessage> _consumer;
        private ConcurrentQueue<TMessage> _messageQueue = new();
        public string kafkaAddress;
        public string topicName;
        private CancellationTokenSource _cts = new();

        public void Start()
        {
            Init();
            StartKafkaThread();
        }
        

        public void OnDisable()
        {
            StopKafkaThread();
        }

        public void OnApplicationQuit()
        {
            StopKafkaThread();
        }

        private void StartKafkaThread()
        {
            if (_kafkaThread is { IsAlive: true }) return;

            _consumer = new KafkaConsumer<TMessage>(kafkaAddress, topicName, ReceiveMessage);
            _kafkaThread = new Thread(() => _consumer.StartKafkaListener(_cts.Token));

            _kafkaThread.Start();
        }

        public void Update()
        {
            TMessage message;
            while (_messageQueue.TryDequeue(out message))
            {
                OnMessage(message);
            }
        }

        private void ReceiveMessage(TMessage message)
        {
            _messageQueue.Enqueue(message);
        }

        protected virtual void Init()
        {
            
        }

        protected abstract void OnMessage(TMessage message);

        void StopKafkaThread()
        {
            if (_kafkaThread.IsAlive)
            {
                _cts.Cancel();
                _kafkaThread.Join();
            }
        }
    }
}