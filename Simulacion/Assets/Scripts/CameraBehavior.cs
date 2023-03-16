using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class CameraBehavior : MonoBehaviour
{
    //Movimiento: W A S D
    //Altura: Q E
    //Correr: Shift
    //Mover camara: Mantener Click Derecho(Mouse1)
    //Seleccionar vehiculo: Click Izquierdo(Mouse0)
    //Cambiar entre tercer y primera persona: Space
    //Entrar en camara libre: Escape

    //VELOCIDADES DE LA CAMARA
    public float speed = 10;

    //Aumento de la velocidad al pulsar Shift
    public int speedMultiplier = 50;

    //Nos permite tener dos aumentos de velocidad: el deseado y el "normal" siendo 1
    private int speedMulti;

    //SEGUIMIENTO DE UN OBJETO
    public Transform follow;

    //Distancia a la que querremos seguir el carro
    public float followDistance = 200;

    //Distnacia para poder seleccionar un carro
    public float selectionDistance = 2000;

    //Vector para la camara que rota alrededor del carro
    private Vector2 angle = new Vector2(90 * Mathf.Deg2Rad, 0);

    //Vector de sensibilidad en X y Y
    public Vector2 sensibility;

    //Nos permite saber si nos encontramos en modo de primera persona o no
    private bool firstPerson = false;

    //CAMARA LIBRE
    Vector3 currentEulerAngles;

    //LIMITES DE LA CAMARA
    //X
    public float xLimit = 1000;

    //Y
    public float yMinLimit = 5;

    public float yMaxLimit = 100;

    //Z
    public float zLimit = 1000;

    //Obtener las corrdenadas del cursor y convertirlas en direccion

    void Update()
    {
        //Evita que la camara valla mas alla del limite establecido en X
        if (transform.position.x < -xLimit)
        {
            transform.position = new Vector3(-xLimit, transform.position.y, transform.position.z);
        }

        if (transform.position.x > xLimit)
        {
            transform.position = new Vector3(xLimit, transform.position.y, transform.position.z);
        }

        //Evita que la camara valla mas alla de los limites establecidos en Y
        transform.position = new Vector3(
            transform.position.x,
            Mathf.Clamp(transform.position.y, yMinLimit, yMaxLimit),
            transform.position.z);
        //Evita que la camara valla mas alla del limite establecido en X
        if (transform.position.x < -zLimit)
        {
            transform.position = new Vector3(transform.position.x, transform.position.y, -zLimit);
        }

        if (transform.position.x > zLimit)
        {
            transform.position = new Vector3(transform.position.x, transform.position.y, zLimit);
        }

        //Raycast nos permite poder interactiar con los collider de los objetos, en este caso verificamos que pertenerzcan a la etiqueta "Vehicles"
        RaycastHit hit;
        if (Physics.Raycast(Camera.main.ScreenPointToRay(Input.mousePosition), out hit, selectionDistance))
        {
            //De ser un objeto con la etiqueta "Vehicles", obtiene del metodo "GetObjectToFollo()" la posicion del objeto y lo pasa al nuestro objeto "follow"
            if (hit.collider.tag == "Vehicles" && Input.GetKey(KeyCode.Mouse0) && follow == null)
            {
                follow = hit.collider.transform;
            }
        }

        //Mantener clic derecho, girar la camara libre
        if (Input.GetKey(KeyCode.Mouse1) && follow == null)
        {
            //Posicion del cursor para camara libre
            float hor = Input.GetAxis("Mouse X");
            float ver = Input.GetAxis("Mouse Y");
            if (hor != 0 || ver != 0)
            {
                //Esto nos permite rotar libremente en el eje X y limitar la rotacion en el eje Y entre 80 y -80
                Vector3 rotation = transform.localEulerAngles;
                rotation.y = rotation.y + hor * sensibility.x;
                rotation.x = (rotation.x - ver * sensibility.y + 360) % 360;
                if (rotation.x > 80 && rotation.x < 180)
                {
                    rotation.x = 80;
                }
                else if (rotation.x < 280 && rotation.x > 180)
                {
                    rotation.x = 280;
                }

                transform.localEulerAngles = rotation;
            }
        }

        //Mantener clic derecho, orbitar camara al estar fija en un objeto
        if (Input.GetKey(KeyCode.Mouse1) && follow != null)
        {
            //Posicion en X del cursor para rotar alrededor de un objeto
            float hor = Input.GetAxis("Mouse X");
            if (hor != 0)
            {
                angle.x += hor * Mathf.Deg2Rad * sensibility.x;
            }

            //Posicion en Y del cursor para rotar alrededor de un objeto
            float ver = Input.GetAxis("Mouse Y");
            if (ver != 0)
            {
                angle.y += ver * Mathf.Deg2Rad * sensibility.y;
                angle.y = Mathf.Clamp(angle.y, -80 * Mathf.Deg2Rad, 80 * Mathf.Deg2Rad);
            }
        }

        //Al estar siguiendo un carro y pulsar Space, entras a vista en primera persona
        if (Input.GetKeyDown(KeyCode.Space) && follow != null)
        {
            if (firstPerson == false)
            {
                firstPerson = true;
            }
            else
            {
                firstPerson = false;
            }
        }

        //Movimiento de la camara en primera persona
        if (follow != null && firstPerson == true)
        {
            transform.position = follow.GetChild(0).transform.position;
            transform.rotation = follow.transform.rotation;
        }

        //Dejar de seguir
        if (Input.GetKeyDown(KeyCode.Escape))
        {
            firstPerson = false;
            follow = null;
        }

        //Movimientos de la camara libre
        if (Input.GetKey(KeyCode.W)) //Adelante
        {
            transform.position += transform.forward * speedMulti * speed * Time.deltaTime;
        }

        if (Input.GetKey(KeyCode.S)) //Atras
        {
            transform.position -= transform.forward * speedMulti * speed * Time.deltaTime;
        }

        if (Input.GetKey(KeyCode.D)) //Derecha
        {
            transform.position += transform.right * speedMulti * speed * Time.deltaTime;
        }

        if (Input.GetKey(KeyCode.A)) //Izquierda
        {
            transform.position -= transform.right * speedMulti * speed * Time.deltaTime;
        }

        if (Input.GetKey(KeyCode.E)) //Arriba
        {
            transform.position += transform.up * speedMulti * speed * Time.deltaTime;
        }

        if (Input.GetKey(KeyCode.Q)) //Abajo
        {
            transform.position -= transform.up * speedMulti * speed * Time.deltaTime;
        }

        if (Input.GetKey(KeyCode.LeftShift)) //Aumenta la velocidad
        {
            speedMulti = speedMultiplier;
        }

        if (!Input.GetKey(KeyCode.LeftShift)) //El aumento de velocidad regresa a 1
        {
            speedMulti = 1;
        }
    }

    void LateUpdate()
    {
        if (follow != null &&
            firstPerson ==
            false) //Rotar la camara alrededor del obejto cuando se sigue y se esta en vista de tercera persona
        {
            Vector3 orbit = new Vector3(
                Mathf.Cos(angle.x) * Mathf.Cos(angle.y),
                -Mathf.Sin(angle.y),
                -Mathf.Sin(angle.x) * Mathf.Cos(angle.y));
            transform.position = follow.position + orbit * followDistance;
            transform.rotation = Quaternion.LookRotation(follow.position - transform.position);
        }
    }
}