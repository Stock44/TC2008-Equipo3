using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class SelectVehicle : MonoBehaviour
{
    //Cada carro debe llevar un Box Collider y ajustarlo a que lo cubra
    //Ademas de ponerles la etiqueta "Vehicles"
    //Y asignarles un Hijo a los carros que sea un objeto vacio ubicado en donde querremos la vista en primera persona

    //Metodo que nos permite obtener las coordenadas de cada objeto
    public Transform GetObjectToFollow()
    {
        return gameObject.transform;
    }
}
