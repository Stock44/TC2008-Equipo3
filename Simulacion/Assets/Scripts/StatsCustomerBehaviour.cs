using System;
using System.Collections;
using System.Collections.Generic;
using Kafka;
using TMPro;
using UnityEngine;

public class StatsMessage
{
    public int vehicle_count;
    public float average_speed;
    public float entries_per_second;
    public float exits_per_second;
    public float people_entry_per_second;
    public float people_exit_per_second;
}

public class StatsCustomerBehaviour : KafkaConsumerBehaviour<StatsMessage>
{
    public GameObject vehicleCountObject;
    public GameObject averageSpeedObject;
    public GameObject vehiclesObject;
    public GameObject peopleObject;

    private TMP_Text _vehicleCountText;
    private TMP_Text _averageSpeedText;
    private TMP_Text _vehiclesText;
    private TMP_Text _peopleText;

    protected override void Init()
    {
        _vehicleCountText = vehicleCountObject.GetComponent<TMP_Text>();
        _averageSpeedText = averageSpeedObject.GetComponent<TMP_Text>();
        _vehiclesText = vehiclesObject.GetComponent<TMP_Text>();
        _peopleText = peopleObject.GetComponent<TMP_Text>();
    }

    protected override void OnMessage(StatsMessage message)
    {
        _vehicleCountText.text = "Vehicle count: " + message.vehicle_count + " vehicles";
        _averageSpeedText.text = "Average vehicle speed: " + message.average_speed + " m/s";
        _vehiclesText.text = "Vehicles | entries: " + message.entries_per_second + " vehicles/s | exits: " +
                             message.exits_per_second + " vehicles/s";
        _peopleText.text = "People | entries: " + message.people_entry_per_second + " people/s | exits: " +
                           message.people_exit_per_second + " people/s";
    }
}