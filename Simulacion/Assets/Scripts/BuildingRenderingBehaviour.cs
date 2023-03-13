using System.Collections;
using System.Collections.Generic;
using Kafka;
using UnityEngine;
using UnityEngine.ProBuilder;
using UnityEngine.ProBuilder.MeshOperations;

public class BuildingMessage
{
    public List<float> geometry_x;
    public List<float> geometry_y;
    public int levels;
    public string name;
}

public class BuildingRenderingBehaviour : KafkaConsumerBehaviour<BuildingMessage>
{
    private int nextId = 0;
    public Material buildingMaterial;

    protected override void OnMessage(BuildingMessage message)
    {
        var building = new GameObject("building" + nextId);
        building.transform.parent = transform;
        nextId++;

        List<Vector3> geometry = new();

        for (int i = 0; i < message.geometry_y.Count; i++)
        {
            var x = message.geometry_x[i];
            var y = message.geometry_y[i];
            geometry.Add(new Vector3(x, 0.0f, y));
        }

        var mesh = building.AddComponent<ProBuilderMesh>();
        building.GetComponent<MeshRenderer>().material = buildingMaterial;
        
        var levels = message.levels == 0 ? 2 : message.levels;
        mesh.CreateShapeFromPolygon(geometry, levels * 4.0f, false);
    }
}