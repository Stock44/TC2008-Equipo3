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
        public float x_direction;
        public float y_direction;
        public float z_direction;
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
        public int vehicle_type;
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
    private Dictionary<int, Vector3> _vehicleDirections = new();
    private Dictionary<int, float> _vehicleSpeeds = new();

    public string kafkaAddress;
    public string updateTopicName;
    public string creationTopicName;
    public string deletionTopicName;

    public List<GameObject> vehicleTypes;

    private CancellationTokenSource _cts = new();


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
        if (_creationThread is not { IsAlive: true })
        {
            _vehicleCreationsConsumer = new(kafkaAddress, creationTopicName, ReceiveCreationMessage);
            _creationThread = new Thread(() => _vehicleCreationsConsumer.StartKafkaListener(_cts.Token));
            _creationThread.Start();
        }

        if (_updateThread is not { IsAlive: true })
        {
            _vehicleUpdatesConsumer = new(kafkaAddress, updateTopicName, ReceiveUpdateMessage);
            _updateThread = new Thread(() => _vehicleUpdatesConsumer.StartKafkaListener(_cts.Token));
            _updateThread.Start();
        }

        if (_deletionThread is not { IsAlive: true })
        {
            _vehicleDeletionsConsumer = new(kafkaAddress, deletionTopicName, ReceiveDeletionMessage);
            _deletionThread = new Thread(() => _vehicleDeletionsConsumer.StartKafkaListener(_cts.Token));
            _deletionThread.Start();
        }
    }

    public void Update()
    {
        while (_creationQueue.TryDequeue(out var creation))
        {
            var vehiclePrefab = vehicleTypes[creation.vehicle_type];
            var newVehicle = Instantiate(vehiclePrefab, transform);
            _vehicleObjects.Add(creation.id, newVehicle);
            _vehicleDirections.Add(creation.id, new Vector3());
            _vehicleSpeeds.Add(creation.id, 0.0f);
        }

        while (_updateQueue.TryDequeue(out var update))
        {
            if (!_vehicleObjects.ContainsKey(update.id))
            {
                continue;
            }
            var newPosition = new Vector3(update.x, update.y, update.z);
            _vehicleSpeeds[update.id] = update.speed;
            _vehicleObjects[update.id].transform.position = newPosition;
            Vector3 direction = new(update.x_direction, update.y_direction, update.z_direction);
            _vehicleDirections[update.id] = direction;
            _vehicleObjects[update.id].transform.rotation = Quaternion.LookRotation(direction);
        }

        while (_deletionQueue.TryDequeue(out var deletion))
        {
            Destroy(_vehicleObjects[deletion.id]);
            _vehicleObjects.Remove(deletion.id);
            _vehicleSpeeds.Remove(deletion.id);
            _vehicleDirections.Remove(deletion.id);
        }

        foreach (var (vehicleId, vehicle) in _vehicleObjects)
        {
            var vehicleSpeed = _vehicleSpeeds[vehicleId];
            var vehicleDirection = _vehicleDirections[vehicleId];

            vehicle.transform.position += vehicleDirection * (vehicleSpeed * Time.deltaTime);
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
        _creationQueue.Clear();
        _deletionQueue.Clear();
        _updateQueue.Clear();

        _cts.Cancel();
        if (_creationThread.IsAlive)
        {
            _creationThread.Join();
        }

        if (_deletionThread.IsAlive)
        {
            _deletionThread.Join();
        }

        if (_updateThread.IsAlive)
        {
            _updateThread.Join();
        }

        _cts = new();
    }
}