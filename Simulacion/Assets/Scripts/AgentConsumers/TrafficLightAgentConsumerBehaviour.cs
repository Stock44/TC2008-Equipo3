using System;
using System.Collections.Generic;
using Kafka;
using UnityEngine;

namespace AgentConsumers
{
    [Serializable]
    public class TrafficLightAgentState
    {
        public int id;
        public int x;
        public int y;
        public int color; // 0 red 1 yellow 2 green
    }

    public class TrafficLightAgentConsumerBehaviour : KafkaConsumerBehaviour<TrafficLightAgentState>
    {
        public GameObject carPrefab;
        private Dictionary<int, GameObject> _trafficLightObjects = new();

        protected override void OnMessage(TrafficLightAgentState message)
        {
            GameObject carObject;

            if (_trafficLightObjects.ContainsKey(message.id))
            {
                carObject = _trafficLightObjects[message.id];
            }
            else
            {
                carObject = Instantiate(carPrefab, this.transform);
                _trafficLightObjects.Add(message.id, carObject);
            }

            var newPosition = new Vector3(message.x, 0, message.y);
            carObject.transform.position = newPosition;

            Color color;
            switch (message.color)
            {
                case 0:
                    color = Color.red;
                    break;
                case 1:
                    color = Color.yellow;
                    break;
                case 2:
                    color = Color.green;
                    break;
                default:
                    Debug.LogError("unknown color received");
                    color = Color.magenta;
                    break;
            }

            carObject.GetComponent<MeshRenderer>().material.color = color;
        }
    }
}