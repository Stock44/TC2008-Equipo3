using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using Kafka;
using UnityEngine;

public class VehicleSpawnerBehaviour : MonoBehaviour
{
    public class VehicleUpdateMessage
    {
        public int id;
        public float x;
        public float y;
        public float z;
        public float acceleration;
        public float speed;
    }

    public class VehicleDeletionMessage
    {
        public int id;
    }

    public class VehicleCreationMessage
    {
        public int id;
    }

    private Thread _creationThread;
    private Thread _updateThread;
    private Thread _deletionThread;
    private KafkaConsumer<VehicleUpdateMessage> _vehicleUpdatesConsumer;
    private ConcurrentQueue<VehicleUpdateMessage> _updateQueue = new();

    private KafkaConsumer<VehicleCreationMessage> _vehicleCreationsConsumer;
    private ConcurrentQueue<VehicleCreationMessage> _creationQueue = new();

    private KafkaConsumer<VehicleDeletionMessage> _vehicleDeletionsConsumer;
    private ConcurrentQueue<VehicleDeletionMessage> _deletionQueue = new();

    private Dictionary<int, GameObject> _vehicleObjects = new();

    public string kafkaAddress;
    public string updateTopicName;
    public string creationTopicName;
    public string deletionTopicName;

    public GameObject vehiclePrefab;


    public void Start()
    {
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
        _vehicleDeletionsConsumer = new(kafkaAddress, deletionTopicName, ReceiveDeletionMessage);
        _vehicleCreationsConsumer = new(kafkaAddress, creationTopicName, ReceiveCreationMessage);
        _vehicleUpdatesConsumer = new(kafkaAddress, updateTopicName, ReceiveUpdateMessage);
        _creationThread = new Thread(_vehicleCreationsConsumer.StartKafkaListener);
        _updateThread = new Thread(_vehicleUpdatesConsumer.StartKafkaListener);
        _deletionThread = new Thread(_vehicleDeletionsConsumer.StartKafkaListener);


        _creationThread.Start();
        _updateThread.Start();
        _deletionThread.Start();
    }

    public void Update()
    {
        VehicleCreationMessage creation;
        while (_creationQueue.TryDequeue(out creation))
        {
            var newVehicle = Instantiate(vehiclePrefab, transform);
            _vehicleObjects.Add(creation.id, newVehicle);
        }

        VehicleUpdateMessage update;
        while (_updateQueue.TryDequeue(out update))
        {
            var newPosition = new Vector3(update.x, update.z, update.y);
            _vehicleObjects[update.id].transform.position = newPosition;
        }

        VehicleDeletionMessage deletion;
        while (_deletionQueue.TryDequeue(out deletion))
        {
            _vehicleObjects.Remove(deletion.id);
        }
    }

    private void ReceiveCreationMessage(VehicleCreationMessage message)
    {
        _creationQueue.Enqueue(message);
    }

    private void ReceiveUpdateMessage(VehicleUpdateMessage message)
    {
        _updateQueue.Enqueue(message);
    }

    private void ReceiveDeletionMessage(VehicleDeletionMessage message)
    {
        _deletionQueue.Enqueue(message);
    }

    void StopKafkaThread()
    {
        _creationThread.Abort();
        _deletionThread.Abort();
        _updateThread.Abort();

        _creationThread.Join();
        _deletionThread.Join();
        _updateThread.Join();
    }
}