using System;
using System.Collections.Generic;
using Kafka;
using UnityEngine;

namespace AgentConsumers
{
    [Serializable]
    public class FieldAgentState
    {
        public int id;
        public int x;
        public int y;
    }

    public class FieldAgentConsumerBehaviour : KafkaConsumerBehaviour<FieldAgentState>
    {
        public GameObject carPrefab;
        private Dictionary<int, GameObject> _carObjects = new();

        protected override void OnMessage(FieldAgentState message)
        {
            GameObject carObject;

            if (_carObjects.ContainsKey(message.id))
            {
                carObject = _carObjects[message.id];
            }
            else
            {
                carObject = Instantiate(carPrefab, this.transform);
                _carObjects.Add(message.id, carObject);
            }

            var newPosition = new Vector3(message.x, 0, message.y);
            carObject.transform.position = newPosition;
        }
    }
}