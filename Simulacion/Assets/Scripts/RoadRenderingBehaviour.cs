using System.Collections;
using System.Collections.Generic;
using System.Numerics;
using Kafka;
using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.ProBuilder;
using Vector3 = UnityEngine.Vector3;

public class RoadMessage
{
    public float start_x;
    public float start_y;
    public float end_x;
    public float end_y;
    public float length;
    public int lane_count;
}

public class RoadRenderingBehaviour : KafkaConsumerBehaviour<RoadMessage>
{
    public GameObject laneObject;
    public float laneWidth;

    protected override void OnMessage(RoadMessage message)
    {
        float offset = Mathf.Floor(message.lane_count / 2.0f);
        if (message.lane_count % 2 > 0)
        {
            offset += 0.5f;
        }

        offset -= message.lane_count;
        offset *= laneWidth;
        
        for (int lane = 0; lane < message.lane_count; lane++)
        {
            laneObject = Instantiate(laneObject, transform);

            Vector3 startPosition = new(message.start_x, 0.0f, message.start_y);
            Vector3 endPosition = new(message.end_x, 0.0f, message.end_y);
            Vector3 directionVector = endPosition - startPosition;
            directionVector = directionVector.normalized;
            Vector3 laneCentroid = (startPosition + directionVector * (message.length / 2));
            
            offset += laneWidth;
            var normalVector = Vector3.Cross(Vector3.up, directionVector);
            laneCentroid += normalVector * offset;

            laneObject.transform.position = laneCentroid;
            float angle = Vector3.SignedAngle(Vector3.right, directionVector.normalized, Vector3.up);
            laneObject.transform.eulerAngles = new Vector3(0.0f, angle, 0.0f);
            laneObject.transform.localScale = new Vector3(message.length, 0.1f, laneWidth);
        }
    }
}