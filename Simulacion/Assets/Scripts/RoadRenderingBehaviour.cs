using System.Collections;
using System.Collections.Generic;
using System.Numerics;
using Kafka;
using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.ProBuilder;
using Quaternion = UnityEngine.Quaternion;
using Vector3 = UnityEngine.Vector3;

public class RoadMessage
{
    public float start_x;
    public float start_y;
    public float start_z;
    public float end_x;
    public float end_y;
    public float end_z;
    public float length;
    public int lane_count;
}

public class RoadRenderingBehaviour : KafkaConsumerBehaviour<RoadMessage>
{
    public GameObject laneObject;
    public float laneWidth;

    protected override void OnMessage(RoadMessage message)
    {
        Vector3 startPosition = new(message.start_x, message.start_y, message.start_z);
        Vector3 endPosition = new(message.end_x, message.end_y, message.end_z);
        var displacement = endPosition - startPosition;
        var direction = displacement.normalized;
        var normalVector = Vector3.Cross(direction, Vector3.up);
        Vector3 roadCentroid = startPosition + (direction * (message.length / 2.0f));
        // float zAngle = Vector3.SignedAngle(Vector3.forward, direction, Vector3.right);
        float yAngle = Vector3.SignedAngle(Vector3.right, direction, Vector3.up);
        float xAngle = Vector3.SignedAngle(Vector3.right, direction, Vector3.forward);

        float offset = -Mathf.Floor(message.lane_count / 2.0f);

        offset *= laneWidth;

        for (int lane = 0; lane < message.lane_count; lane++)
        {
            laneObject = Instantiate(laneObject, transform);

            var laneCentroid = roadCentroid + normalVector * offset;
            laneObject.transform.position = laneCentroid;
            laneObject.transform.rotation = Quaternion.LookRotation(direction) * Quaternion.Euler(0.0f, 90.0f, 0.0f);
            laneObject.transform.localScale = new Vector3(message.length, 0.2f, laneWidth);

            offset += laneWidth;
        }
    }
}